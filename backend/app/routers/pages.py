from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import SessionDep, SettingsDep
from app.models import Job, Page, Patch, TextBlock
from app.schemas import HistoryOut, HistoryStep, JobOut, MaskEdit, PageOut, PagePatch
from app.services import history, patches, title
from app.services.cleaning import Stroke, edit_mask
from app.services.page_import import delete_page_files

router = APIRouter(prefix="/api/pages", tags=["pages"])

# fajlovi stranica imaju jedinstvena imena i nikad se ne menjaju
IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def get_page(session: Session, page_id: int) -> Page:
    page = session.get(Page, page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stranica ne postoji")
    return page


@router.patch("/{page_id}")
def update_page(page_id: int, data: PagePatch, session: SessionDep) -> PageOut:
    page = get_page(session, page_id)
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(page, field, value)
    session.commit()
    return page


@router.get("/{page_id}/image")
def page_image(page_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    page = get_page(session, page_id)
    return FileResponse(Path(settings.data_dir, page.image_path), headers=IMMUTABLE)


@router.get("/{page_id}/thumbnail")
def page_thumbnail(page_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    page = get_page(session, page_id)
    path = Path(settings.data_dir, page.thumbnail_path)
    return FileResponse(path, media_type="image/webp", headers=IMMUTABLE)


@router.get("/{page_id}/clean-image")
def page_clean_image(page_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    """Očišćena slika; menja se pri svakom čišćenju, pa ide sa ?v=cleaned_at iz frontenda."""
    page = get_page(session, page_id)
    if not page.clean_path:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stranica još nije očišćena")
    return FileResponse(Path(settings.data_dir, page.clean_path), headers=IMMUTABLE)


@router.post("/{page_id}/mask")
def edit_page_mask(
    page_id: int, data: MaskEdit, session: SessionDep, settings: SettingsDep
) -> PageOut:
    """Potezi četkice: „add" briše još teksta bojom okoline, „erase" vraća original."""
    page = get_page(session, page_id)
    strokes = [Stroke(s.mode, s.radius, list(s.points)) for s in data.strokes]
    edit_mask(session, settings, page, strokes)
    return page


@router.get("/{page_id}/history")
def page_history(page_id: int, session: SessionDep) -> HistoryOut:
    """Nazivi radnji koje „Poništi" i „Ponovi" trenutno vraćaju (za dugmad u editoru)."""
    return HistoryOut(**history.state(session, get_page(session, page_id)))


@router.post("/{page_id}/undo")
def undo_page(page_id: int, session: SessionDep, settings: SettingsDep) -> HistoryStep:
    return _step(session, settings, page_id, "undo")


@router.post("/{page_id}/redo")
def redo_page(page_id: int, session: SessionDep, settings: SettingsDep) -> HistoryStep:
    return _step(session, settings, page_id, "redo")


def _step(session: Session, settings: SettingsDep, page_id: int, kind: str) -> HistoryStep:
    page = get_page(session, page_id)
    action = history.step(session, page, kind, Path(settings.data_dir))
    blocks = session.scalars(
        select(TextBlock).where(TextBlock.page_id == page.id).order_by(TextBlock.position)
    )
    return HistoryStep(action=action, blocks=list(blocks), **history.state(session, page))


@router.post("/{page_id}/clean", status_code=status.HTTP_202_ACCEPTED)
def clean_page_request(page_id: int, session: SessionDep) -> JobOut:
    page = get_page(session, page_id)
    job = Job(type="clean_page", project_id=page.project_id, payload={"page_id": page_id})
    session.add(job)
    session.commit()
    return job


@router.delete("/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(page_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    page = get_page(session, page_id)
    session.delete(page)
    session.flush()
    remaining = session.scalars(
        select(Page)
        .where(Page.project_id == page.project_id, Page.kind == page.kind)
        .order_by(Page.position)
    )
    for position, other in enumerate(remaining, start=1):
        other.position = position
    session.commit()
    delete_page_files(Path(settings.data_dir), page)
    # slova naslova ostaju i posle brisanja bloka (zbog „Poništi"); ovde odlaze ona bez bloka
    live = session.scalars(
        select(TextBlock.id).join(Page).where(Page.project_id == page.project_id)
    )
    title.sweep(Path(settings.data_dir), page.project_id, set(live))
    kept = session.execute(
        select(Patch.path, Patch.mask_path).join(Page).where(Page.project_id == page.project_id)
    )
    patches.sweep(Path(settings.data_dir), page.project_id, {p for row in kept for p in row if p})
    return Response(status_code=status.HTTP_204_NO_CONTENT)
