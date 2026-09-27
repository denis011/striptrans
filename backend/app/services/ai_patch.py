"""AI prepravka natpisa (B1): model za slike crta prevod istim slovima na isečku originala.

Isečak originala sa marginom ide modelu uz originalni tekst i prevod; vraćena slika se svede na
veličinu isečka i čuva kao predlog. Prihvaćen predlog postaje zakrpa, ali samo unutrašnjost okvira
bloka (sa mekom ivicom), jer model menja i okolinu natpisa (docs/benchmarks/ai-natpisi.md).
"""

import io
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Page, Patch, TextBlock
from app.services import patches
from app.services.glossary_suggest import flatten
from app.services.openrouter import OpenRouterClient

AI_KINDS = {"title", "other", "sfx"}  # naslovi, natpisi i onomatopeje; oblačići se slažu fontom
MARGIN = 0.12  # isečak je veći od bloka: model vidi okolinu i crta u istoj razmeri
FEATHER = 6  # meka ivica zakrpe (px): prelaz ka stranici ispod
KIND_NAMES = {
    "title": "story title or lettered caption",
    "other": "painted sign or lettering",
    "sfx": "sound effect drawn over the artwork",
}


class AiPatchError(Exception):
    pass


def crop_box(page: Page, block: TextBlock) -> tuple[int, int, int, int]:
    """Isečak oko bloka sa marginom, unutar stranice."""
    mx, my = block.width * MARGIN, block.height * MARGIN
    x0, y0 = max(0, int(block.x - mx)), max(0, int(block.y - my))
    x1 = min(page.width, int(round(block.x + block.width + mx)))
    y1 = min(page.height, int(round(block.y + block.height + my)))
    return x0, y0, x1 - x0, y1 - y0


PROMPT = """This is a crop of a page from an Italian comic book: a {what}. Replace the Italian
lettering "{source}" with the Serbian translation "{target}" (Latin script, keep the letters
Č Ć Ž Š Đ exactly). Draw it in exactly the same lettering style: same letter shapes, weight, slant,
outline, fill, shadow and texture, same colours, same size and the same position and angle. Where
the new text is shorter, restore the background or artwork behind the removed letters. Keep
everything else (artwork, lines, background) exactly as it is. The new lettering must read exactly
"{target}": {count} letters, {spelled}; no other letters and no leftovers of the old ones. Return
only the edited image with the same aspect ratio."""


def build_prompt(block: TextBlock) -> str:
    target = " ".join(block.translation.split())
    letters = [char for char in target if char.isalpha()]
    return PROMPT.format(
        what=KIND_NAMES[block.kind],
        source=flatten(block.text),
        target=target,
        count=len(letters),
        spelled="-".join(letters),
    ).replace("\n", " ")


def proposal_path(data_dir: Path, project_id: int, job_id: int) -> Path:
    return data_dir / "projects" / str(project_id) / "ai" / f"{job_id}.png"


def make_proposal(
    client: OpenRouterClient,
    settings: Settings,
    page: Page,
    block: TextBlock,
    quality: str,
    job_id: int,
) -> dict:
    """Pozovi model i sačuvaj predlog iste veličine kao isečak; vraća opis za rezultat posla."""
    if block.kind not in AI_KINDS:
        raise AiPatchError("AI prepravka je za naslove, natpise i onomatopeje")
    if not block.translation.strip() or not block.text.strip():
        raise AiPatchError("blok nema originalni tekst ili prevod")
    data_dir = Path(settings.data_dir)
    box = crop_box(page, block)
    original = patches.crop(data_dir, page, box, clean=False)
    model = settings.ai_image_model if quality == "quality" else settings.ai_image_cheap_model
    started = time.monotonic()
    image, cost = client.edit_image(build_prompt(block), original, model)
    with Image.open(io.BytesIO(original)) as source, Image.open(io.BytesIO(image)) as result:
        # crno-bele strane ostaju sive; model uvek vraća boju i svoju veličinu
        mode = "L" if source.mode in ("L", "1", "LA") else "RGB"
        fitted = result.convert(mode).resize(source.size, Image.LANCZOS)
    target = proposal_path(data_dir, page.project_id, job_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    fitted.save(target, "PNG")
    return {
        "block_id": block.id,
        "image": str(target.relative_to(data_dir)),
        "box": list(box),
        "model": model,
        "cost": cost,
        "seconds": round(time.monotonic() - started, 1),
    }


CHANGE = 40  # razlika sive (0–255) od koje je piksel predloga izmenjen u odnosu na original
REACH = 0.5  # nova slova smeju da izađu iz okvira do ovoliko njegove širine/visine (SWACK → SCVAK)


def change_mask(
    original: np.ndarray, proposal: np.ndarray, block: tuple[int, int, int, int]
) -> np.ndarray:
    """Gde zakrpa važi: ceo okvir bloka (stara slova moraju nestati) i izmene predloga koje se na
    njega nastavljaju, do `REACH` širine i visine bloka van okvira; ostale izmene se ne prenose."""
    left, top, width, height = block
    changed = np.abs(proposal.astype(np.int16) - original.astype(np.int16)) > CHANGE
    changed = cv2.dilate(changed.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
    count, labels = cv2.connectedComponents(changed.astype(np.uint8), connectivity=8)
    inside = np.zeros_like(changed)
    inside[top : top + height, left : left + width] = True
    touching = np.unique(labels[inside & changed])
    mask = np.isin(labels, touching[touching > 0]) & changed
    rx, ry = int(round(width * REACH)), int(round(height * REACH))
    near = np.zeros_like(changed)
    near[max(0, top - ry) : top + height + ry, max(0, left - rx) : left + width + rx] = True
    return (mask & near) | inside


def masked(
    proposal: Image.Image, mask: np.ndarray, feather: int = FEATHER
) -> tuple[Image.Image, tuple]:
    """Predlog sa providnošću po maski (meka ivica prati slova), isečen na deo gde maska postoji."""
    grown = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32)
    alpha = cv2.GaussianBlur(grown, (0, 0), max(1.0, feather / 2)) * 255
    alpha[mask] = 255
    ys, xs = np.nonzero(alpha > 1)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    rgba = proposal.convert("RGBA")
    rgba.putalpha(Image.fromarray(np.clip(alpha, 0, 255).astype(np.uint8)))
    return rgba.crop((x0, y0, x1, y1)), (x0, y0, x1 - x0, y1 - y0)


def accept(session: Session, data_dir: Path, page: Page, block: TextBlock, result: dict) -> Patch:
    """Predlog postaje zakrpa iznad složenog teksta (da se ne vidi dvaput): okvir bloka i nova slova
    koja iz njega izlaze, ali ne i izmene crteža dalje od natpisa."""
    x0, y0, width, height = result["box"]
    original = Image.open(io.BytesIO(patches.crop(data_dir, page, (x0, y0, width, height), False)))
    with Image.open(data_dir / result["image"]) as proposal:
        proposal = proposal.resize(original.size)
        inner = (
            int(round(block.x - x0)),
            int(round(block.y - y0)),
            int(round(block.width)),
            int(round(block.height)),
        )
        mask = change_mask(
            np.asarray(original.convert("L")), np.asarray(proposal.convert("L")), inner
        )
        piece, (px, py, pw, ph) = masked(proposal, mask)
    buffer = io.BytesIO()
    piece.save(buffer, "PNG")
    box = {"x": x0 + px, "y": y0 + py, "width": pw, "height": ph}
    patch = patches.add(session, data_dir, page, buffer.getvalue(), box)
    patch.above_text = True
    session.flush()
    return patch
