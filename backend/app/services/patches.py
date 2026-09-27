"""Zakrpe slikom (Faza 6c): PNG napravljen van aplikacije se postavlja preko stranice.

Služi za ono što automatika ne pokrije: table sa teksturom, logotipe, složene naslove, panel
doteran u GIMP-u. Izvoz crta zakrpe istim redom kao editor, pa je pregled jednak izvozu.
"""

import io
import uuid
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Page, Patch

MAX_BYTES = 25 * 1024 * 1024
TYPES = {"PNG": ".png", "WEBP": ".webp", "JPEG": ".jpg"}
MIN_SIZE = 4.0  # zakrpa ne sme da bude manja od ovoliko piksela stranice


class PatchRejected(Exception):
    """Fajl nije upotrebljiva slika."""


def patch_dir(data_dir: Path, project_id: int) -> Path:
    return data_dir / "projects" / str(project_id) / "patches"


def page_patches(session: Session, page_id: int) -> list[Patch]:
    query = select(Patch).where(Patch.page_id == page_id)
    return list(session.scalars(query.order_by(Patch.position, Patch.id)))


def _fit(width: float, height: float, page: Page) -> tuple[float, float, float, float]:
    """Okvir nove zakrpe: prava veličina, u sredini stranice (uklopljena ako je veća od nje)."""
    scale = min(1.0, page.width / max(width, 1), page.height / max(height, 1))
    box = (width * scale, height * scale)
    return ((page.width - box[0]) / 2, (page.height - box[1]) / 2, box[0], box[1])


def add(
    session: Session, data_dir: Path, page: Page, data: bytes, box: dict | None = None
) -> Patch:
    """Snimi sliku i dodaj je kao zakrpu na vrh stranice."""
    if len(data) > MAX_BYTES:
        raise PatchRejected("slika je prevelika (najviše 25 MB)")
    try:
        with Image.open(io.BytesIO(data)) as image:
            extension = TYPES.get(image.format or "")
            size = image.size
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise PatchRejected("fajl nije slika") from exc
    if extension is None:
        raise PatchRejected("slika mora biti PNG, WebP ili JPG")
    relative = Path("projects", str(page.project_id), "patches", uuid.uuid4().hex + extension)
    target = data_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    x, y, width, height = _fit(size[0], size[1], page)
    top = max((patch.position for patch in page_patches(session, page.id)), default=0)
    patch = Patch(
        page_id=page.id,
        position=top + 1,
        path=str(relative),
        x=(box or {}).get("x", x),
        y=(box or {}).get("y", y),
        width=(box or {}).get("width", width),
        height=(box or {}).get("height", height),
    )
    session.add(patch)
    session.flush()
    return patch


def crop(data_dir: Path, page: Page, box: tuple[float, float, float, float], clean: bool) -> bytes:
    """Isečak stranice u punoj rezoluciji (PNG), za doradu van aplikacije."""
    relative = page.clean_path if clean and page.clean_path else page.image_path
    x, y, width, height = (int(round(value)) for value in box)
    x, y = max(0, min(x, page.width - 1)), max(0, min(y, page.height - 1))
    width = max(1, min(width, page.width - x))
    height = max(1, min(height, page.height - y))
    with Image.open(data_dir / relative) as image:
        piece = image.crop((x, y, x + width, y + height))
        buffer = io.BytesIO()
        piece.save(buffer, "PNG")
    return buffer.getvalue()


def sweep(data_dir: Path, project_id: int, keep: set[str]) -> None:
    """Obriši slike zakrpa kojih više nema u bazi (obrisana stranica)."""
    folder = patch_dir(data_dir, project_id)
    if not folder.is_dir():
        return
    for file in folder.iterdir():
        if (
            file.is_file()
            and str(Path("projects", str(project_id), "patches", file.name)) not in keep
        ):
            file.unlink(missing_ok=True)
