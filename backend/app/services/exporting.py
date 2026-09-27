"""Izvoz albuma (Faza 5b): prijem nacrtanih stranica i pakovanje u CBZ, PDF ili ZIP.

Browser crta stranice istim kodom kao editor i šalje ih kao PNG (bez gubitaka); ovde se svaka
kodira tačno jednom u izabrani format, a crno-bele strane ostaju sive (manji fajl).
"""

import io
import re
import shutil
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

import img2pdf
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Export, Page, Project, TextBlock, utcnow

PDF_DPI = 300  # strana 1801×2457 px ≈ 15×21 cm (uobičajen format italijanskog stripa)
EXTENSIONS = {"jpeg": "jpg", "png": "png"}


class ExportError(ValueError):
    """Neispravna stranica ili izvoz koji nije u odgovarajućem stanju."""


def album_pages(
    session: Session, project_id: int, skipped: str, first: int | None, last: int | None
):
    """Stranice originala u albumu, redom; preskočene (naslovna, reklame) po izboru korisnika."""
    pages = session.scalars(
        select(Page)
        .where(Page.project_id == project_id, Page.kind == "original")
        .order_by(Page.position)
    ).all()
    return [
        page
        for page in pages
        if (first is None or page.position >= first)
        and (last is None or page.position <= last)
        and not (page.skip and skipped == "omit")
    ]


def export_dir(data_dir: str, export: Export) -> Path:
    return Path(data_dir, "exports", str(export.id))


def page_file(data_dir: str, export: Export, index: int) -> Path:
    return export_dir(data_dir, export) / "pages" / f"{index:03d}.{EXTENSIONS[export.image_format]}"


def _is_gray(path: Path) -> bool:
    with Image.open(path) as image:
        return image.mode in ("L", "1", "LA")


def encode(image: Image.Image, gray: bool, image_format: str, quality: int) -> bytes:
    image = image.convert("L" if gray else "RGB")
    buffer = io.BytesIO()
    if image_format == "jpeg":
        image.save(buffer, "JPEG", quality=quality, optimize=True, dpi=(PDF_DPI, PDF_DPI))
    else:
        image.save(buffer, "PNG", optimize=True, dpi=(PDF_DPI, PDF_DPI))
    return buffer.getvalue()


def receive_page(data_dir: str, export: Export, page: Page, data: bytes) -> None:
    """Nacrtana stranica iz browsera: mora imati dimenzije originala."""
    if export.status != "uploading":
        raise ExportError("izvoz više ne prima stranice")
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            if image.size != (page.width, page.height):
                raise ExportError(
                    f"stranica {page.position} je {image.size[0]}×{image.size[1]}, "
                    f"a original {page.width}×{page.height}"
                )
            gray = _is_gray(Path(data_dir, page.image_path))
            encoded = encode(image, gray, export.image_format, export.quality)
    except (OSError, SyntaxError) as exc:
        raise ExportError(f"stranica {page.position} nije ispravna slika") from exc
    index = export.positions.index(page.position) + 1
    target = page_file(data_dir, export, index)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(encoded)
    if page.position not in export.received:
        export.received = [*export.received, page.position]


def album_name(project: Project) -> str:
    """„Ramon 12 - Dolina tišine" (bez znakova koji ne smeju u ime fajla)."""
    parts = [project.series.name, project.issue_number or ""]
    title = project.translated_title or project.original_title
    name = " ".join(part for part in parts if part).strip()
    if title:
        name = f"{name} - {title}"
    return re.sub(r'[\\/:*?"<>|]+', "", name).strip() or "album"


def comic_info(project: Project, page_count: int) -> str:
    fields = {
        "Series": project.series.name,
        "Number": project.issue_number or "",
        "Title": project.translated_title or project.original_title or "",
        "LanguageISO": project.series.target_lang or "sr",
        "PageCount": str(page_count),
        "Notes": "Prevod i lettering: StripTrans",
    }
    body = "".join(f"  <{key}>{escape(value)}</{key}>\n" for key, value in fields.items() if value)
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ComicInfo xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">\n'
        f"{body}</ComicInfo>\n"
    )


def pack(session: Session, data_dir: str, export: Export, report=lambda done, total: None) -> None:
    """Dopuni preskočene stranice originalom i spakuj album; posao workera."""
    project = session.get(Project, export.project_id)
    pages = {
        page.position: page
        for page in session.scalars(
            select(Page).where(Page.project_id == export.project_id, Page.kind == "original")
        )
    }
    files: list[Path] = []
    total = len(export.positions)
    for index, position in enumerate(export.positions, start=1):
        target = page_file(data_dir, export, index)
        page = pages.get(position)
        if not target.exists():
            if page is None:
                raise ExportError(f"stranica {position} više ne postoji")
            if not page.skip:
                raise ExportError(f"stranica {position} nije nacrtana")
            source = Path(data_dir, page.image_path)  # preskočena: original bez izmena
            with Image.open(source) as image:
                data = encode(image, _is_gray(source), export.image_format, export.quality)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        files.append(target)
        report(index, total)
    name = album_name(project)
    folder = export_dir(data_dir, export)
    if export.format == "pdf":
        result = folder / f"{name}.pdf"
        # slike idu u PDF bez ponovne kompresije, strana je veličine slike na 300 dpi
        layout = img2pdf.get_fixed_dpi_layout_fun((PDF_DPI, PDF_DPI))
        result.write_bytes(img2pdf.convert([str(path) for path in files], layout_fun=layout))
    else:
        result = folder / f"{name}.{'cbz' if export.format == 'cbz' else 'zip'}"
        with zipfile.ZipFile(result, "w", zipfile.ZIP_STORED) as archive:
            for path in files:
                archive.write(path, path.name)
            if export.format == "cbz":
                archive.writestr("ComicInfo.xml", comic_info(project, len(files)))
    shutil.rmtree(folder / "pages", ignore_errors=True)
    export.path = str(result.relative_to(data_dir))
    export.size = result.stat().st_size
    export.status = "done"
    export.finished_at = utcnow()
    session.commit()


def readiness(session: Session, project_id: int) -> list[dict]:
    """Šta nije spremno za izvoz, po stranici (upozorenje, ne zabrana)."""
    pages = session.scalars(
        select(Page)
        .where(Page.project_id == project_id, Page.kind == "original")
        .order_by(Page.position)
    ).all()
    result = []
    for page in pages:
        blocks = session.scalars(select(TextBlock).where(TextBlock.page_id == page.id)).all()
        dialogue = [
            b for b in blocks if b.kind in ("speech", "thought", "caption") and b.text.strip()
        ]
        result.append(
            {
                "position": page.position,
                "page_id": page.id,
                "skip": page.skip,
                "cleaned": page.cleaned_at is not None,
                "reviewed": page.translation_reviewed,
                "blocks": len(dialogue),
                "untranslated": sum(1 for b in dialogue if not b.translation.strip()),
            }
        )
    return result


STALE_SECONDS = 90  # bez nove stranice ovoliko dugo: tab sa izvozom je verovatno zatvoren
ABANDONED_SECONDS = 3600  # posle sat vremena se izvoz koji se ne crta više ne prikazuje


def drawing_progress(session: Session, data_dir: str, export: Export) -> dict:
    """Crtanje albuma u browseru: koliko je nacrtanih stranica stiglo i kad je stigla poslednja."""
    drawn = set(
        session.scalars(
            select(Page.position).where(
                Page.project_id == export.project_id,
                Page.kind == "original",
                Page.position.in_(export.positions),
                Page.skip.is_(False),
            )
        )
    )
    folder = export_dir(data_dir, export) / "pages"
    times = [path.stat().st_mtime for path in folder.iterdir()] if folder.is_dir() else []
    created = export.created_at.replace(tzinfo=UTC).timestamp()
    last = max([created, *times])
    idle = time.time() - last
    return {
        "done": len(drawn & set(export.received)),
        "total": len(drawn),
        "last": datetime.fromtimestamp(last, UTC).replace(tzinfo=None),
        "stale": idle > STALE_SECONDS,
        "abandoned": idle > ABANDONED_SECONDS,
    }
