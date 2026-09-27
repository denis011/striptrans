"""Čišćenje originalnog teksta (Faza 4a): tekst u oblačićima se prekriva bojom pozadine oblačića.

Slova u oblačiću su tamni delovi unutar okvira teksta koji ne dodiruju njegovu ivicu (ivica
oblačića i rep je dodiruju), bez modela. Maska neobaveznog modela za tekst služi samo za
onomatopeje preko crteža.
Natpisi i onomatopeje preko crteža se ovde ne diraju: bela ispuna bi razmazala crtež
(to radi inpainting u 4d).
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Page, utcnow
from app.services import history, title
from app.services.geometry import Box
from app.services.inpaint import artwork_mask, inpaint, needs_inpaint, text_angle
from app.services.page_processing import sfx_model_path, unread
from app.services.sfx import text_mask

CLEAN_KINDS = {"speech", "thought", "caption"}
MASK_THRESHOLD = 0.2  # niži prag od predloga onomatopeja: bolje obrisati i bledu ivicu slova
DILATE = 7  # hvata poluprovidne ivice slova, da ne ostane „senka" teksta
MARGIN = 6  # okvir bloka ume da bude tesan oko teksta


FAINT = 3  # tamnije od papira za manje od ovoga: bleda ivica slova, ne crtež
HALO = 40  # ostaci slova se traže najviše ovoliko piksela od maske
HALO_INK = 150  # tamnije od ovoga je mastilo: obris oblačića, crtež, promašeno slovo

WHITE = 200  # svetlije od ovoga je unutrašnjost oblačića
SHAPE_STEP = 3  # razmak izmerenih redova oblika oblačića (px)
SHAPE_REACH = 0.5  # oblik se meri najviše pola okvira levo, desno, iznad i ispod teksta
SHAPE_GROW = 1.3  # red širi od ovoliko puta najšireg izmerenog (ili okvira): izašli smo iz oblačića
SHAPE_NARROW = 0.2  # red uži od ovog dela najšireg: kraj oblačića (rep, vrh)


def _white_run(line: np.ndarray, low: int, high: int, x: int) -> tuple[int, int] | None:
    """Beli niz u redu koji sadrži stupac `x`, unutar [low, high]; None ako x nije beo."""
    if not line[x]:
        return None
    left_dark = np.flatnonzero(~line[low:x])
    right_dark = np.flatnonzero(~line[x : high + 1])
    left = low + (left_dark[-1] + 1 if len(left_dark) else 0)
    right = x + (right_dark[0] - 1 if len(right_dark) else high - x)
    return int(left), int(right)


def _next_run(
    line: np.ndarray, low: int, high: int, span: tuple[int, int]
) -> tuple[int, int] | None:
    """Beli niz u sledećem redu koji se najviše poklapa sa `span` iz prethodnog reda.

    Traži se samo ispod prethodnog reda, pa se oblik ne može prebaciti na nepovezanu belinu.
    """
    best: tuple[int, tuple[int, int]] | None = None
    x = span[0]
    while x <= span[1]:
        run = _white_run(line, low, high, x)
        if run is None:
            x += 1
            continue
        overlap = min(run[1], span[1]) - max(run[0], span[0]) + 1
        if best is None or overlap > best[0]:
            best = (overlap, run)
        x = run[1] + 1
    return best[1] if best else None


def bubble_shape(gray: np.ndarray, box: Box) -> list[list[float]] | None:
    """Beli prostor oko teksta, red po red: poligon (levi rub odozgo, pa desni odozdo).

    Slagač iz njega zna koliko je svaki red oblačića širok i gde mu je sredina, pa tekst
    ne izlazi iz oblačića ni kad ga lik ili rep oblačića „zaseca". Beli prostor se prati iz
    reda u red (naracija zna da bude stepenasta, pa sredina ne mora da ostane bela do kraja).
    """
    x, y, w, h = box
    height, width = gray.shape
    cx, cy = int(x + w / 2), int(y + h / 2)
    if not (0 <= cx < width and 0 <= cy < height):
        return None
    white = gray > WHITE
    low_x, high_x = max(int(x - w * SHAPE_REACH), 0), min(int(x + w * (1 + SHAPE_REACH)), width - 1)
    low_y, high_y = (
        max(int(y - h * SHAPE_REACH), 0),
        min(int(y + h * (1 + SHAPE_REACH)), height - 1),
    )
    start = _white_run(white[cy], low_x, high_x, cx)
    if start is None:
        return None
    widest = start[1] - start[0] + 1
    rows: dict[int, tuple[int, int]] = {cy: start}
    for direction in (-1, 1):
        span, row = start, cy
        while True:
            row += direction * SHAPE_STEP
            if not (low_y <= row <= high_y):
                break
            run = _next_run(white[row], low_x, high_x, span)
            if run is None:
                break
            span_width = run[1] - run[0] + 1
            # oblačić ume da bude mnogo širi od reda u kom je merenje počelo (lik ga tu zaseca),
            # pa se širenje meri i prema okviru bloka, a ne samo prema dotad najširem redu
            if span_width > SHAPE_GROW * max(widest, w) or span_width < SHAPE_NARROW * widest:
                break  # izašli smo iz oblačića, ili mu je ovde kraj
            widest = max(widest, span_width)
            rows[row] = run
            span = run
    if len(rows) < 2:
        return None
    ordered = sorted(rows)
    return [[float(rows[r][0]), float(r)] for r in ordered] + [
        [float(rows[r][1]), float(r)] for r in reversed(ordered)
    ]


def faint_halo(pixels: np.ndarray, region: np.ndarray, paper: float) -> np.ndarray:
    """Blede ivice obrisanih slova: mrlje uz masku koje nisu čist papir ni pravo mastilo.

    Detektor uhvati jezgro slova, ali meka ivica (siva 240–252) ostane i pri zumiranju se vidi
    kao „duh" originalnog teksta. Briše se samo ono do čega se od maske stiže bez prelaska preko
    mastila (dakle unutar oblačića) i najviše HALO piksela od nje, pa crtež ostaje netaknut.
    """
    gray = pixels if pixels.ndim == 2 else cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
    faint = (gray < paper - FAINT) & ~region
    if not faint.any():
        return np.zeros_like(region)
    # unutrašnjost oblačića: sve što je uz masku i do njega se stiže bez prelaska preko mastila
    light = (gray >= HALO_INK) | region
    _, labels = cv2.connectedComponents(light.astype(np.uint8), connectivity=8)
    inside = np.isin(labels, list(set(np.unique(labels[region]).tolist()) - {0}))
    near = cv2.dilate(region.astype(np.uint8), np.ones((HALO * 2 + 1,) * 2, np.uint8)).astype(bool)
    return faint & inside & near


@dataclass
class CleanResult:
    blocks: int = 0  # očišćeni blokovi
    pixels: int = 0  # prekriveni pikseli
    inpainted: int = 0  # onomatopeje i natpisi obrisani preko crteža


INK = 190  # tamnije od ovoga u oblačiću je slovo (i njegova siva ivica)
INK_MARGIN = 0.06  # okvir se proširi za ovoliko (+4 px), da tesan okvir ne preseče slovo


def ink_letters(image: np.ndarray, blocks: list[tuple[str, Box]]) -> np.ndarray:
    """Slova oblačića bez modela: u okviru teksta (uz marginu) tamni delovi koji ne dodiruju ivicu
    okvira i nisu skoro visoki kao okvir (ivica oblačića, rep, crtež koji ulazi u okvir).

    Isto kao maska modela za tekst: na 30 strana ostaje isto mastila posle čišćenja.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY) if image.ndim == 3 else image
    height, width = gray.shape
    letters = np.zeros((height, width), np.float32)
    for kind, (x, y, w, h) in blocks:
        if kind not in CLEAN_KINDS:
            continue
        mx, my = int(w * INK_MARGIN) + 4, int(h * INK_MARGIN) + 4
        x0, y0 = max(int(x) - mx, 0), max(int(y) - my, 0)
        x1, y1 = min(int(x + w) + mx, width), min(int(y + h) + my, height)
        region = gray[y0:y1, x0:x1]
        count, labels, stats, _ = cv2.connectedComponentsWithStats(
            (region < INK).astype(np.uint8), connectivity=8
        )
        keep = np.zeros(count, bool)
        for index in range(1, count):
            cx, cy, cw, ch, _ = stats[index]
            touches = cx == 0 or cy == 0 or cx + cw >= region.shape[1] or cy + ch >= region.shape[0]
            keep[index] = not touches and ch < 0.9 * region.shape[0]
        np.maximum(letters[y0:y1, x0:x1], keep[labels], out=letters[y0:y1, x0:x1])
    return letters


def clean_image(
    image: np.ndarray, blocks: list[tuple[str, Box]], probability: np.ndarray
) -> tuple[np.ndarray, np.ndarray, CleanResult]:
    """Vrati očišćenu sliku (RGB), masku prekrivenih piksela i broj očišćenih blokova."""
    height, width = probability.shape
    text = cv2.dilate(
        (probability > MASK_THRESHOLD).astype(np.uint8), np.ones((DILATE, DILATE), np.uint8)
    ).astype(bool)
    cleaned = image.copy()
    covered = np.zeros((height, width), dtype=bool)
    result = CleanResult()
    for kind, (x, y, w, h) in blocks:
        if kind not in CLEAN_KINDS:
            continue
        x0, y0 = max(int(x) - MARGIN, 0), max(int(y) - MARGIN, 0)
        x1, y1 = min(int(x + w) + MARGIN, width), min(int(y + h) + MARGIN, height)
        region = text[y0:y1, x0:x1]
        if not region.any():
            continue
        pixels = cleaned[y0:y1, x0:x1]
        rest = pixels[~region]
        # pozadina oblačića: medijana onoga što nije tekst (kod ovakvih stripova skoro uvek bela)
        paper = np.median(rest, axis=0) if len(rest) else 255
        pixels[region] = paper
        halo = faint_halo(pixels, region, float(np.mean(paper)))
        pixels[halo] = paper
        covered[y0:y1, x0:x1] |= region | halo
        result.blocks += 1
    result.pixels = int(covered.sum())
    return cleaned, covered, result


def clean_paths(page: Page) -> tuple[str, str]:
    """Relativne putanje očišćene slike i maske (pored originala projekta)."""
    stem = Path(page.image_path).stem
    base = Path("projects", str(page.project_id))
    return str(base / "clean" / f"{stem}.png"), str(base / "masks" / f"{stem}.png")


def remeasure_shapes(session: Session, settings: Settings, page: Page) -> int:
    """Ponovo izmeri oblike oblačića iz već očišćene strane; vraća broj promenjenih blokova.

    Oblik se inače meri pri čišćenju. Ovo je za slučaj kad se pravilo merenja promeni ili kad je
    okvir bloka pomeren posle čišćenja — slika se ne dira, pa nema ponovnog LaMa posla.
    """
    if not page.clean_path:
        return 0
    blocks = [block for block in page.blocks if block.kind in CLEAN_KINDS]
    if not blocks:
        return 0
    with Image.open(Path(settings.data_dir) / page.clean_path) as image:
        gray = np.asarray(image.convert("L"))
    shapes = {
        block.id: bubble_shape(gray, (block.x, block.y, block.width, block.height))
        for block in blocks
    }
    changed = [block for block in blocks if shapes[block.id] != block.bubble_polygon]
    if not changed:
        return 0
    history.record(session, page, "ponovno merenje oblačića")
    for block in changed:
        block.bubble_polygon = shapes[block.id]
    session.commit()
    return len(changed)


def clean_page(session: Session, settings: Settings, page: Page) -> CleanResult:
    data_dir = Path(settings.data_dir)
    # nepročitan blok nema šta da upiše, pa se original ispod njega ne briše
    blocks = [
        (block.kind, (block.x, block.y, block.width, block.height))
        for block in page.blocks
        if not unread(block)
    ]
    with Image.open(data_dir / page.image_path) as original:
        mode = "L" if original.mode in ("L", "1", "LA") else "RGB"  # crno-bele strane ostaju sive
        rgb = original.convert("RGB")
    pixels = np.asarray(rgb)
    cleaned, covered, result = clean_image(pixels, blocks, ink_letters(pixels, blocks))
    model = sfx_model_path(settings)  # neobavezan: bez njega maska onomatopeja je samo od mastila
    probability = (
        text_mask(rgb, model) if model.exists() else np.zeros(pixels.shape[:2], np.float32)
    )
    original_gray = np.asarray(rgb.convert("L"))
    for block in page.blocks:
        if block.kind != "title":
            continue
        # naslov: tačno isečena slova, bojom trake (ili LaMa ako traka nije jednobojna)
        letters = title.refresh(block, data_dir, original_gray)
        if letters is None or not needs_inpaint(block.kind, block.text, block.translation):
            continue
        if letters.uniform:
            cleaned[letters.mask] = round(letters.background)
        else:
            cleaned = inpaint(cleaned, letters.mask, settings.models_dir)
        covered |= letters.mask
        block.angle = 0.0
        result.inpainted += 1
    for block in page.blocks:
        if block.kind == "title" or not needs_inpaint(block.kind, block.text, block.translation):
            continue
        box = (block.x, block.y, block.width, block.height)
        letters = artwork_mask(original_gray, probability, box, block.kind)
        cleaned = inpaint(cleaned, letters, settings.models_dir)
        covered |= letters
        block.angle = text_angle(letters) if block.kind == "sfx" else 0.0
        result.inpainted += 1
    result.pixels = int(covered.sum())
    gray = np.asarray(Image.fromarray(cleaned).convert("L"))
    for block in page.blocks:
        box = (block.x, block.y, block.width, block.height)
        if block.kind in CLEAN_KINDS:
            block.bubble_polygon = bubble_shape(gray, box)
        block.dark_background = dark_background(gray, box)
    clean_path, mask_path = clean_paths(page)
    outputs = (
        (clean_path, Image.fromarray(cleaned).convert(mode)),
        (mask_path, Image.fromarray(covered.astype(np.uint8) * 255).convert("1")),
    )
    for relative, image in outputs:
        target = data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, optimize=True)
    page.clean_path, page.mask_path = clean_path, mask_path
    session.flush()  # izmene blokova (oblik, podloga) dobijaju vreme pre vremena čišćenja
    page.cleaned_at = utcnow()
    session.commit()
    return result


RING = 7  # boja za dodatu masku: medijana okoline (prsten ove širine oko poteza)
DARK = 100  # medijana sive ispod ovoga: tamna podloga (npr. naslov belim slovima na crnom)


def dark_background(gray: np.ndarray, box: Box) -> bool:
    """Da li je podloga bloka posle čišćenja tamna, pa prevod treba slagati svetlim slovima."""
    x, y, w, h = box
    region = gray[max(int(y), 0) : int(y + h), max(int(x), 0) : int(x + w)]
    return bool(region.size) and float(np.median(region)) < DARK


@dataclass
class Stroke:
    mode: str  # add (obriši još) | erase (vrati original)
    radius: float
    points: list[tuple[float, float]]


def stroke_mask(shape: tuple[int, int], stroke: Stroke) -> np.ndarray:
    canvas = np.zeros(shape, dtype=np.uint8)
    radius = max(1, round(stroke.radius))
    points = [(round(x), round(y)) for x, y in stroke.points]
    for start, end in zip(points, points[1:], strict=False):
        cv2.line(canvas, start, end, 1, thickness=radius * 2)
    for point in points:
        cv2.circle(canvas, point, radius, 1, thickness=-1)
    return canvas.astype(bool)


def apply_strokes(
    original: np.ndarray, cleaned: np.ndarray, covered: np.ndarray, strokes: list[Stroke]
) -> tuple[np.ndarray, np.ndarray]:
    """Ručna ispravka maske: „add" prekriva bojom okoline, „erase" vraća piksele originala."""
    cleaned, covered = cleaned.copy(), covered.copy()
    for stroke in strokes:
        area = stroke_mask(covered.shape, stroke)
        if stroke.mode == "erase":
            restore = area & covered
            cleaned[restore] = original[restore]
            covered &= ~area
            continue
        new = area & ~covered
        if not new.any():
            continue
        ring = cv2.dilate(new.astype(np.uint8), np.ones((RING * 2 + 1,) * 2, np.uint8)).astype(bool)
        ring &= ~new & ~covered
        surround = cleaned[ring]
        cleaned[new] = np.median(surround, axis=0) if len(surround) else 255
        covered |= new
    return cleaned, covered


def stroke_bounds(shape: tuple[int, int], strokes: list[Stroke]) -> tuple[int, int, int, int]:
    """Okvir svih poteza (sa poluprečnikom), unutar stranice: toliko se pamti za „Poništi"."""
    height, width = shape
    radius = max(stroke.radius for stroke in strokes)
    xs = [x for stroke in strokes for x, _ in stroke.points]
    ys = [y for stroke in strokes for _, y in stroke.points]
    x0 = max(0, int(min(xs) - radius) - 2)
    y0 = max(0, int(min(ys) - radius) - 2)
    x1 = min(width, int(max(xs) + radius) + 3)
    y1 = min(height, int(max(ys) + radius) + 3)
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


def edit_mask(session: Session, settings: Settings, page: Page, strokes: list[Stroke]) -> None:
    """Primeni poteze četkice na masku stranice i ponovo izračunaj oblik oblačića."""
    data_dir = Path(settings.data_dir)
    with Image.open(data_dir / page.image_path) as source:
        mode = "L" if source.mode in ("L", "1", "LA") else "RGB"
        original = np.asarray(source.convert(mode))
    if page.clean_path and page.mask_path:
        with (
            Image.open(data_dir / page.clean_path) as clean,
            Image.open(data_dir / page.mask_path) as mask,
        ):
            cleaned = np.asarray(clean.convert(mode))
            covered = np.asarray(mask.convert("L")) > 127
    else:
        cleaned, covered = original.copy(), np.zeros(original.shape[:2], dtype=bool)
        page.clean_path, page.mask_path = clean_paths(page)
    patch = (
        history.image_patch(data_dir, page, stroke_bounds(covered.shape, strokes))
        if strokes
        else None
    )
    history.record(session, page, "potez četkicom", patch, data_dir)
    for stroke in strokes:
        if stroke.mode == "inpaint":  # preko crteža: LaMa umesto boje okoline
            area = stroke_mask(covered.shape, stroke)
            rgb = cleaned if cleaned.ndim == 3 else np.stack([cleaned] * 3, axis=-1)
            filled = inpaint(np.ascontiguousarray(rgb), area, settings.models_dir)
            cleaned = filled if cleaned.ndim == 3 else filled[..., 0]
            covered = covered | area
        else:
            cleaned, covered = apply_strokes(original, cleaned, covered, [stroke])
    gray = cleaned if cleaned.ndim == 2 else np.asarray(Image.fromarray(cleaned).convert("L"))
    for block in page.blocks:
        if block.kind in CLEAN_KINDS:
            block.bubble_polygon = bubble_shape(gray, (block.x, block.y, block.width, block.height))
    for relative, image in (
        (page.clean_path, Image.fromarray(cleaned)),
        (page.mask_path, Image.fromarray(covered.astype(np.uint8) * 255).convert("1")),
    ):
        target = data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target, optimize=True)
    session.flush()
    page.cleaned_at = utcnow()
    session.commit()
