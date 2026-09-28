from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.deps import SessionDep, SettingsDep
from app.models import Patch
from app.routers.pages import get_page
from app.schemas import PatchMaskEdit, PatchOut, PatchPatch
from app.services import history, patches

router = APIRouter(prefix="/api", tags=["patches"])

IMMUTABLE = {"Cache-Control": "public, max-age=31536000, immutable"}


def get_patch(session: Session, patch_id: int) -> Patch:
    patch = session.get(Patch, patch_id)
    if patch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "zakrpa ne postoji")
    return patch


@router.get("/pages/{page_id}/patches")
def list_patches(page_id: int, session: SessionDep) -> list[PatchOut]:
    get_page(session, page_id)
    return patches.page_patches(session, page_id)


@router.post("/pages/{page_id}/patches", status_code=status.HTTP_201_CREATED)
async def add_patch(
    page_id: int,
    session: SessionDep,
    settings: SettingsDep,
    file: Annotated[UploadFile, File()],
    x: Annotated[float | None, Form()] = None,
    y: Annotated[float | None, Form()] = None,
    width: Annotated[float | None, Form()] = None,
    height: Annotated[float | None, Form()] = None,
    match_page: Annotated[bool, Form()] = False,
    above_text: Annotated[bool, Form()] = False,
) -> PatchOut:
    """Dodaj PNG (ili WebP/JPG) kao zakrpu; uz `match_page` je siva na crno-beloj strani."""
    page = get_page(session, page_id)
    box = None
    if None not in (x, y, width, height):
        box = {"x": x, "y": y, "width": width, "height": height}
    history.record(session, page, "nova zakrpa")
    try:
        data = await file.read()
        patch = patches.add(
            session, Path(settings.data_dir), page, data, box, match_page, above_text
        )
    except patches.PatchRejected as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    session.commit()
    return patch


@router.patch("/patches/{patch_id}")
def update_patch(patch_id: int, data: PatchPatch, session: SessionDep) -> PatchOut:
    patch = get_patch(session, patch_id)
    history.record(session, patch.page, "izmena zakrpe")
    for field, value in data.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(patch, field, value)
    patch.width = max(patches.MIN_SIZE, patch.width)
    patch.height = max(patches.MIN_SIZE, patch.height)
    session.commit()
    return patch


@router.delete("/patches/{patch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patch(patch_id: int, session: SessionDep) -> Response:
    patch = get_patch(session, patch_id)
    history.record(session, patch.page, "brisanje zakrpe")
    # slika ostaje: „Poništi" vraća zakrpu; briše se kad se obriše stranica
    session.delete(patch)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/patches/{patch_id}/image")
def patch_image(patch_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    patch = get_patch(session, patch_id)
    path = Path(settings.data_dir, patch.path)
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "slika zakrpe ne postoji")
    if patch.mask_path:  # adresa sadrži verziju maske, pa i ovaj odgovor sme u keš
        image = patches.masked_image(Path(settings.data_dir), patch)
        return Response(image, media_type="image/png", headers=IMMUTABLE)
    return FileResponse(path, headers=IMMUTABLE)


@router.post("/patches/{patch_id}/mask")
def edit_patch_mask(
    patch_id: int, data: PatchMaskEdit, session: SessionDep, settings: SettingsDep
) -> PatchOut:
    """Četkica po zakrpi: „hide" otkriva ono ispod zakrpe, „show" vraća zakrpu."""
    patch = get_patch(session, patch_id)
    page = get_page(session, patch.page_id)
    history.record(session, page, "četkica po zakrpi")
    strokes = [patches.PatchStroke(s.mode, s.radius, list(s.points)) for s in data.strokes]
    patches.edit_mask(Path(settings.data_dir), page.project_id, patch, strokes)
    session.commit()
    return patch


@router.get("/pages/{page_id}/crop")
def crop_page(
    page_id: int,
    session: SessionDep,
    settings: SettingsDep,
    x: float = 0,
    y: float = 0,
    width: float = 0,
    height: float = 0,
    clean: bool = True,
) -> Response:
    """Isečak stranice u punoj rezoluciji (PNG), za doradu van aplikacije."""
    page = get_page(session, page_id)
    box = (x, y, width or page.width, height or page.height)
    data = patches.crop(Path(settings.data_dir), page, box, clean)
    name = f"strana-{page.position:03d}-isecak.png"
    return Response(
        data,
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
