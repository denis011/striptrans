"""Izvoz albuma: podešavanja, prijem nacrtanih stranica, pakovanje u workeru, preuzimanje."""

import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.deps import SessionDep, SettingsDep
from app.models import Export, Job, Page
from app.routers.projects import get_project
from app.schemas import ExportIn, ExportOut, ExportPage, JobOut, PageReadiness
from app.services.exporting import ExportError, album_pages, export_dir, readiness, receive_page

router = APIRouter(prefix="/api", tags=["exports"])

MAX_PAGE_BYTES = 80 * 1024 * 1024


def get_export(session, export_id: int) -> Export:
    export = session.get(Export, export_id)
    if export is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "izvoz ne postoji")
    return export


@router.get("/projects/{project_id}/export-check")
def export_check(project_id: int, session: SessionDep) -> list[PageReadiness]:
    get_project(session, project_id)
    return [PageReadiness(**item) for item in readiness(session, project_id)]


@router.post("/projects/{project_id}/exports", status_code=status.HTTP_201_CREATED)
def create_export(project_id: int, data: ExportIn, session: SessionDep) -> ExportOut:
    get_project(session, project_id)
    pages = album_pages(session, project_id, data.skipped, data.first, data.last)
    if not pages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "nema stranica za izvoz")
    export = Export(
        project_id=project_id,
        format=data.format,
        image_format=data.image_format,
        quality=data.quality,
        skipped=data.skipped,
        positions=[page.position for page in pages],
        received=[],
        status="uploading",
    )
    session.add(export)
    session.commit()
    out = ExportOut.model_validate(export)
    out.pages = [ExportPage(position=p.position, page_id=p.id, render=not p.skip) for p in pages]
    return out


@router.put("/exports/{export_id}/pages/{position}")
def upload_page(
    export_id: int,
    position: int,
    data: Annotated[bytes, Body(media_type="image/png")],
    session: SessionDep,
    settings: SettingsDep,
) -> ExportOut:
    export = get_export(session, export_id)
    if position not in export.positions:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "stranica nije u ovom izvozu")
    if len(data) > MAX_PAGE_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "stranica je prevelika")
    page = session.scalar(
        select(Page).where(
            Page.project_id == export.project_id, Page.kind == "original", Page.position == position
        )
    )
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stranica ne postoji")
    try:
        receive_page(settings.data_dir, export, page, data)
    except ExportError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    session.commit()
    return export


@router.post("/exports/{export_id}/finish", status_code=status.HTTP_202_ACCEPTED)
def finish_export(export_id: int, session: SessionDep) -> JobOut:
    """Sve nacrtane stranice su poslate: worker dodaje preskočene i pakuje album."""
    export = get_export(session, export_id)
    if export.status != "uploading":
        raise HTTPException(status.HTTP_409_CONFLICT, "izvoz je već završen")
    export.status = "packing"
    job = Job(type="export", project_id=export.project_id, payload={"export_id": export.id})
    session.add(job)
    session.commit()
    return job


@router.get("/projects/{project_id}/exports")
def list_exports(project_id: int, session: SessionDep) -> list[ExportOut]:
    get_project(session, project_id)
    query = select(Export).where(Export.project_id == project_id).order_by(Export.id.desc())
    return list(session.scalars(query))


@router.get("/exports/{export_id}/file")
def export_file(export_id: int, session: SessionDep, settings: SettingsDep) -> FileResponse:
    export = get_export(session, export_id)
    if export.status != "done" or not export.path:
        raise HTTPException(status.HTTP_409_CONFLICT, "izvoz još nije gotov")
    path = Path(settings.data_dir, export.path)
    return FileResponse(path, filename=path.name)


@router.delete("/exports/{export_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_export(export_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    export = get_export(session, export_id)
    shutil.rmtree(export_dir(settings.data_dir, export), ignore_errors=True)
    session.delete(export)
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
