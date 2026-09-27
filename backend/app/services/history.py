"""Poništi i ponovi (Faza 7b): snimci blokova stranice pre svake izmene.

Istorija je na serveru, pa preživi osvežavanje stranice i pokriva sve izmene blokova, i one koje
naprave poslovi u pozadini. Dva niza po stranici: „undo" (snimci pre izmena) i „redo" (snimci
stanja koje je poništeno). Nova izmena briše „redo", kao u svakom editoru.
"""

import uuid
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Page, PageHistory, Patch, TextBlock, utcnow
from app.services import title

LIMIT = 30  # koliko koraka unazad se pamti po stranici
FIELDS = (
    "position",
    "kind",
    "x",
    "y",
    "width",
    "height",
    "bubble_polygon",
    "ocr_text",
    "text",
    "confidence",
    "ocr_model",
    "source",
    "needs_review",
    "translation",
    "translation_model",
    "translation_status",
    "translation_too_long",
    "style",
    "angle",
    "dark_background",
    "title",
)
PATCH_FIELDS = (
    "position",
    "path",
    "x",
    "y",
    "width",
    "height",
    "rotation",
    "opacity",
    "above_text",
)


def snapshot(session: Session, page: Page) -> list[dict]:
    """Stanje svih blokova stranice, onako kako ide u istoriju."""
    blocks = session.scalars(
        select(TextBlock).where(TextBlock.page_id == page.id).order_by(TextBlock.id)
    )
    return [
        {"id": block.id} | {field: getattr(block, field) for field in FIELDS} for block in blocks
    ]


def patch_snapshot(session: Session, page: Page) -> list[dict]:
    """Stanje zakrpa stranice (Faza 6c)."""
    rows = session.scalars(select(Patch).where(Patch.page_id == page.id).order_by(Patch.id))
    return [
        {"id": patch.id} | {field: getattr(patch, field) for field in PATCH_FIELDS}
        for patch in rows
    ]


def patch_dir(data_dir: Path, project_id: int) -> Path:
    return data_dir / "projects" / str(project_id) / "history"


def image_patch(data_dir: Path, page: Page, box: tuple[int, int, int, int]) -> dict | None:
    """Sačuvaj isečak očišćene slike i maske (za „Poništi" poteza četkicom)."""
    files = [page.clean_path, page.mask_path]
    if not all(name and (data_dir / name).exists() for name in files):
        return None  # stranica još nije očišćena: nema šta da se vrati
    x, y, w, h = (int(value) for value in box)
    name = uuid.uuid4().hex
    folder = patch_dir(data_dir, page.project_id)
    folder.mkdir(parents=True, exist_ok=True)
    for relative, suffix in ((page.clean_path, "c"), (page.mask_path, "m")):
        with Image.open(data_dir / relative) as image:
            image.crop((x, y, x + w, y + h)).save(folder / f"{name}{suffix}.png")
    return {"box": [x, y, w, h], "name": name}


def _paste_patch(data_dir: Path, page: Page, patch: dict) -> None:
    """Vrati sačuvani isečak na stranicu i obriši njegove fajlove."""
    x, y, _, _ = patch["box"]
    folder = patch_dir(data_dir, page.project_id)
    for relative, suffix in ((page.clean_path, "c"), (page.mask_path, "m")):
        piece_path = folder / f"{patch['name']}{suffix}.png"
        if not (relative and piece_path.exists()):
            continue
        with Image.open(data_dir / relative) as image:
            whole = image.copy()
        with Image.open(piece_path) as piece:
            whole.paste(piece, (int(x), int(y)))
        whole.save(data_dir / relative, optimize=True)
        piece_path.unlink(missing_ok=True)


def _forget(
    session: Session, data_dir: Path | None, page: Page, entries: list[PageHistory]
) -> None:
    """Obriši zapise istorije stranice zajedno sa njihovim isečcima slike (potezi četkicom)."""
    for entry in entries:
        if entry.patch and data_dir is not None:
            folder = patch_dir(data_dir, page.project_id)
            for suffix in ("c", "m"):
                (folder / f"{entry.patch['name']}{suffix}.png").unlink(missing_ok=True)
        session.delete(entry)
    session.flush()


def _push(
    session: Session,
    page: Page,
    kind: str,
    action: str,
    blocks: list[dict],
    patch: dict | None = None,
    data_dir: Path | None = None,
) -> None:
    top = session.scalar(
        select(func.max(PageHistory.position)).where(
            PageHistory.page_id == page.id, PageHistory.kind == kind
        )
    )
    session.add(
        PageHistory(
            page_id=page.id,
            kind=kind,
            position=(top or 0) + 1,
            action=action,
            blocks=blocks,
            patch=patch,
            patches=patch_snapshot(session, page),
        )
    )
    session.flush()
    extra = session.scalars(
        select(PageHistory)
        .where(PageHistory.page_id == page.id, PageHistory.kind == kind)
        .order_by(PageHistory.position.desc())
        .offset(LIMIT)
    ).all()
    _forget(session, data_dir, page, list(extra))


def _pop(session: Session, page: Page, kind: str) -> PageHistory | None:
    return session.scalar(
        select(PageHistory)
        .where(PageHistory.page_id == page.id, PageHistory.kind == kind)
        .order_by(PageHistory.position.desc())
        .limit(1)
    )


def record(
    session: Session,
    page: Page,
    action: str,
    patch: dict | None = None,
    data_dir: Path | None = None,
) -> None:
    """Zapamti stanje pre izmene. Zove se pre nego što se blokovi promene."""
    _push(session, page, "undo", action, snapshot(session, page), patch, data_dir)
    stale = session.scalars(
        select(PageHistory).where(PageHistory.page_id == page.id, PageHistory.kind == "redo")
    ).all()
    _forget(session, data_dir, page, list(stale))


def _restore_patches(session: Session, page: Page, wanted: list[dict]) -> None:
    """Vrati zakrpe stranice: obrisane se vraćaju sa istim brojem, pa im se vraća i slika."""
    existing = {
        patch.id: patch for patch in session.scalars(select(Patch).where(Patch.page_id == page.id))
    }
    keep = {entry["id"] for entry in wanted}
    for patch_id, patch in existing.items():
        if patch_id not in keep:
            session.delete(patch)
    session.flush()
    for entry in wanted:
        patch = existing.get(entry["id"])
        if patch is None:
            patch = Patch(id=entry["id"], page_id=page.id)
            session.add(patch)
        for field in PATCH_FIELDS:
            setattr(patch, field, entry[field])
    session.flush()


def _restore(session: Session, page: Page, blocks: list[dict], data_dir: Path | None) -> None:
    existing = {
        block.id: block
        for block in session.scalars(select(TextBlock).where(TextBlock.page_id == page.id))
    }
    wanted = {entry["id"]: entry for entry in blocks}
    for block_id, block in existing.items():
        if block_id not in wanted:
            session.delete(block)
    session.flush()
    for entry in blocks:
        block = existing.get(entry["id"])
        if block is None:
            block = TextBlock(id=entry["id"], page_id=page.id)
            session.add(block)
        for field in FIELDS:
            setattr(block, field, entry[field])
    session.flush()
    if data_dir is not None:
        for block in session.scalars(select(TextBlock).where(TextBlock.page_id == page.id)):
            # slike slova starije verzije su možda obrisane: naslov se iseca ponovo
            if block.kind == "title" and block.title and not title.version_exists(block, data_dir):
                title.refresh(block, data_dir)


def step(session: Session, page: Page, kind: str, data_dir: Path | None = None) -> str | None:
    """Poništi (kind „undo") ili ponovi (kind „redo") poslednju izmenu; vrati naziv radnje."""
    entry = _pop(session, page, kind)
    if entry is None:
        return None
    other = "redo" if kind == "undo" else "undo"
    reverse = None
    if entry.patch and data_dir is not None:  # zatečeni isečak ide u suprotni niz
        reverse = image_patch(data_dir, page, entry.patch["box"])
    _push(session, page, other, entry.action, snapshot(session, page), reverse, data_dir)
    _restore(session, page, entry.blocks, data_dir)
    _restore_patches(session, page, entry.patches or [])
    if entry.patch and data_dir is not None:
        _paste_patch(data_dir, page, entry.patch)
        page.cleaned_at = utcnow()  # adresa očišćene slike nosi vreme, pa browser uzima novu
    action = entry.action
    session.delete(entry)
    session.commit()
    return action


def state(session: Session, page: Page) -> dict:
    """Šta „Poništi" i „Ponovi" trenutno mogu (za dugmad u editoru)."""
    result: dict[str, object] = {}
    for kind in ("undo", "redo"):
        entry = _pop(session, page, kind)
        result[kind] = entry.action if entry else None
    return result
