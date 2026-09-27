import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.deps import SessionDep, SettingsDep
from app.models import Export, Job, Page, Project, Series, TextBlock
from app.schemas import (
    ActiveJobOut,
    JobOut,
    PageKind,
    PageOrder,
    PageOut,
    PrepareRequest,
    ProcessRequest,
    ProjectDetail,
    ProjectIn,
    ProjectOut,
    ProjectPatch,
)
from app.services import exporting, script
from app.services.importer import ImportFailed
from app.services.page_import import queue_import

router = APIRouter(prefix="/api", tags=["projects"])


def get_project(session: Session, project_id: int) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "projekat ne postoji")
    return project


def _sorted_pages(project: Project) -> list[Page]:
    return sorted(project.pages, key=lambda page: (page.kind, page.position))


def _summary(project: Project) -> dict:
    originals = [page for page in _sorted_pages(project) if page.kind == "original"]
    return {
        "id": project.id,
        "series": project.series,
        "issue_number": project.issue_number,
        "original_title": project.original_title,
        "translated_title": project.translated_title,
        "created_at": project.created_at,
        "page_count": len(originals),
        "reference_page_count": len(project.pages) - len(originals),
        "cover_page_id": originals[0].id if originals else None,
    }


def _progress(session: Session, project: Project, data_dir: str) -> dict:
    """Koliko je urađeno po koracima; preskočene stranice (naslovna, reklame) se ne broje."""
    originals = [page for page in project.pages if page.kind == "original"]
    active = [page for page in originals if not page.skip]
    ids = [page.id for page in active]
    counts = dict(
        session.execute(
            select(TextBlock.translation_status, func.count())
            .where(TextBlock.page_id.in_(ids), TextBlock.text != "")
            .group_by(TextBlock.translation_status)
        ).all()
    )
    with_blocks = session.scalar(
        select(func.count(func.distinct(TextBlock.page_id))).where(TextBlock.page_id.in_(ids))
    )
    # blokovi koje je detekcija našla, a OCR nije stigao da pročita (prekinuta obrada)
    unread_pages, unread = session.execute(
        select(func.count(func.distinct(TextBlock.page_id)), func.count()).where(
            TextBlock.page_id.in_(ids),
            TextBlock.source == "auto",
            TextBlock.ocr_model.is_(None),
        )
    ).one()
    exported = session.scalar(
        select(func.max(Export.finished_at)).where(
            Export.project_id == project.id, Export.status == "done"
        )
    )
    edited = session.scalar(
        select(func.max(TextBlock.updated_at)).where(TextBlock.page_id.in_(ids))
    )
    # AI prepravke natpisa se plaćaju po pozivu: zbir svih predloga (i odbačenih)
    ai_jobs = session.scalars(
        select(Job).where(
            Job.project_id == project.id, Job.type == "ai_patch", Job.status == "done"
        )
    ).all()
    ai_cost = sum((job.result or {}).get("cost") or 0 for job in ai_jobs)
    cleaned = [page.cleaned_at for page in active if page.cleaned_at]
    changed = max([moment for moment in (edited, *cleaned) if moment], default=None)
    # izvoz u toku: crtanje u browseru ili pakovanje (korak 8 na strani projekta)
    running = session.scalar(
        select(Export)
        .where(Export.project_id == project.id, Export.status.in_(("uploading", "packing")))
        .order_by(Export.id.desc())
        .limit(1)
    )
    export_active = None
    if running is not None and running.status == "packing":
        export_active = {"stage": "packing", "done": 0, "total": 0, "stale": False}
    elif running is not None:
        state = exporting.drawing_progress(session, data_dir, running)
        if not state["abandoned"]:
            export_active = {
                "stage": "drawing",
                "done": state["done"],
                "total": state["total"],
                "stale": state["stale"],
            }
    return {
        "pages": len(active),
        "skipped": sorted(page.position for page in originals if page.skip),
        "with_blocks": (with_blocks or 0) - unread_pages,
        "unread": unread,
        "blocks": sum(counts.values()),
        "translation": counts,
        "proofread": sum(1 for page in active if page.translation_reviewed),
        "cleaned": sum(1 for page in active if page.cleaned_at),
        "exported_at": exported,
        "export_active": export_active,
        "ai_calls": len(ai_jobs),
        "ai_cost": round(ai_cost, 4),
        "changed_at": changed,
    }


def _detail(session: Session, project: Project, data_dir: str) -> ProjectDetail:
    session.refresh(project)
    jobs = session.scalars(
        select(Job).where(Job.project_id == project.id).order_by(Job.id.desc()).limit(10)
    ).all()
    data = {
        **_summary(project),
        "pages": _sorted_pages(project),
        "jobs": jobs,
        "progress": _progress(session, project, data_dir),
    }
    return ProjectDetail.model_validate(data, from_attributes=True)


@router.get("/projects")
def list_projects(session: SessionDep) -> list[ProjectOut]:
    projects = session.scalars(
        select(Project)
        .options(selectinload(Project.pages), selectinload(Project.series))
        .order_by(Project.id.desc())
    )
    return [ProjectOut.model_validate(_summary(p), from_attributes=True) for p in projects]


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectIn, session: SessionDep, settings: SettingsDep) -> ProjectDetail:
    if session.get(Series, data.series_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "serijal ne postoji")
    project = Project(**data.model_dump())
    session.add(project)
    session.commit()
    return _detail(session, project, settings.data_dir)


@router.get("/projects/{project_id}")
def get_project_detail(
    project_id: int, session: SessionDep, settings: SettingsDep
) -> ProjectDetail:
    return _detail(session, get_project(session, project_id), settings.data_dir)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: int, data: ProjectPatch, session: SessionDep, settings: SettingsDep
) -> ProjectDetail:
    project = get_project(session, project_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    session.commit()
    return _detail(session, project, settings.data_dir)


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, session: SessionDep, settings: SettingsDep) -> Response:
    project = get_project(session, project_id)
    exports = session.scalars(select(Export.id).where(Export.project_id == project_id)).all()
    session.delete(project)
    session.commit()
    shutil.rmtree(Path(settings.data_dir, "projects", str(project_id)), ignore_errors=True)
    for export_id in exports:  # izvozi su van foldera projekta
        shutil.rmtree(Path(settings.data_dir, "exports", str(export_id)), ignore_errors=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/script")
def project_script(
    project_id: int,
    session: SessionDep,
    settings: SettingsDep,
    format: str = "html",
    skipped: bool = False,
) -> Response:
    """Scenario za lektora: tabela oblačić po oblačić, kao HTML (za čitanje) ili CSV (za tabelu)."""
    project = get_project(session, project_id)
    if format not in ("html", "csv"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "format mora biti html ili csv")
    if format == "csv":
        data, media = script.to_csv(session, project, skipped), "text/csv; charset=utf-8"
        disposition = "attachment"  # CSV ide u tabelu, HTML se čita u browseru
    else:
        data = script.to_html(session, project, skipped, settings.app_url)
        media, disposition = "text/html; charset=utf-8", "inline"
    name = script.filename(project, format)
    return Response(
        data,
        media_type=media,
        headers={"Content-Disposition": f'{disposition}; filename="{name}"'},
    )


@router.post("/projects/{project_id}/imports", status_code=status.HTTP_202_ACCEPTED)
def import_pages(
    project_id: int,
    files: Annotated[list[UploadFile], File()],
    kind: Annotated[PageKind, Form()],
    session: SessionDep,
    settings: SettingsDep,
) -> JobOut:
    get_project(session, project_id)
    streams = ((upload.filename or "", upload.file) for upload in files)
    try:
        return queue_import(session, settings.data_dir, project_id, kind, streams)
    except ImportFailed as exc:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, str(exc)) from exc


@router.get("/jobs")
def list_active_jobs(session: SessionDep, settings: SettingsDep) -> list[ActiveJobOut]:
    """Poslovi koji rade ili čekaju, redom kojim ih worker uzima; ispred njih crtanje albuma u toku.

    Crtanje albuma nije posao workera (radi ga browser), pa se prikazuje kao posao „export_draw"
    sa negativnim id-jem izvoza; posle njega dolazi pravi posao pakovanja.
    """
    jobs = session.scalars(
        select(Job).where(Job.status.in_(("queued", "running"))).order_by(Job.id)
    ).all()
    drawing = [
        (export, exporting.drawing_progress(session, settings.data_dir, export))
        for export in session.scalars(select(Export).where(Export.status == "uploading"))
    ]
    drawing = [(export, state) for export, state in drawing if not state["abandoned"]]
    ids = {job.project_id for job in jobs} | {export.project_id for export, _ in drawing}
    titles = {
        project.id: script.title(project)
        for project in session.scalars(select(Project).where(Project.id.in_(ids)))
    }
    active = [
        ActiveJobOut(
            id=-export.id,
            type="export_draw",
            status="running",
            project_id=export.project_id,
            progress=state["done"],
            total=state["total"],
            cancel_requested=False,
            error=None,
            result={"stage": "čeka otvoren tab za izvoz"} if state["stale"] else None,
            created_at=export.created_at,
            updated_at=state["last"],
            project_title=titles.get(export.project_id),
        )
        for export, state in drawing
    ]
    return active + [
        ActiveJobOut.model_validate(job).model_copy(
            update={"project_title": titles.get(job.project_id)}
        )
        for job in jobs
    ]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, session: SessionDep) -> JobOut:
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "posao ne postoji")
    return job


@router.get("/projects/{project_id}/pages")
def list_pages(project_id: int, session: SessionDep, kind: PageKind | None = None) -> list[PageOut]:
    project = get_project(session, project_id)
    return [page for page in _sorted_pages(project) if kind is None or page.kind == kind]


@router.put("/projects/{project_id}/pages/order")
def reorder_pages(project_id: int, order: PageOrder, session: SessionDep) -> list[PageOut]:
    get_project(session, project_id)
    pages = session.scalars(
        select(Page).where(Page.project_id == project_id, Page.kind == order.kind)
    ).all()
    by_id = {page.id: page for page in pages}
    if sorted(order.page_ids) != sorted(by_id):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "lista se ne poklapa sa stranicama projekta"
        )
    for position, page_id in enumerate(order.page_ids, start=1):
        by_id[page_id].position = position
    session.commit()
    return sorted(pages, key=lambda page: page.position)


@router.post("/projects/{project_id}/pages/reset-order")
def reset_page_order(project_id: int, session: SessionDep) -> list[PageOut]:
    """Vrati stranice originala i reference u redosled kojim su uvezene."""
    project = get_project(session, project_id)
    counters: dict[str, int] = {}
    for page in sorted(project.pages, key=lambda page: (page.kind, page.import_order)):
        counters[page.kind] = counters.get(page.kind, 0) + 1
        page.position = counters[page.kind]
    session.commit()
    return _sorted_pages(project)


@router.post("/projects/{project_id}/process", status_code=status.HTTP_202_ACCEPTED)
def process_project_request(
    project_id: int, session: SessionDep, settings: SettingsDep, data: ProcessRequest | None = None
) -> JobOut:
    """Obrada svih stranica originala; bez `replace` preskače stranice koje već imaju blokove."""
    get_project(session, project_id)
    data = data or ProcessRequest()
    job = Job(
        type="process_project",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "model": data.model or settings.ocr_model,
            "replace": data.replace,
        },
    )
    session.add(job)
    session.commit()
    return job


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, session: SessionDep) -> JobOut:
    job = get_job(job_id, session)
    if job.status == "queued":
        job.status = "cancelled"
    elif job.status == "running":
        job.cancel_requested = True
    session.commit()
    return job


@router.post("/projects/{project_id}/translate", status_code=status.HTTP_202_ACCEPTED)
def translate_project_request(
    project_id: int, session: SessionDep, settings: SettingsDep, data: ProcessRequest | None = None
) -> JobOut:
    """Prevod svih stranica; bez `replace` preskače blokove koji već imaju prevod."""
    get_project(session, project_id)
    data = data or ProcessRequest()
    job = Job(
        type="translate_project",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "model": data.model or settings.translation_model,
            "replace": data.replace,
        },
    )
    session.add(job)
    session.commit()
    return job


@router.post("/projects/{project_id}/shapes", status_code=status.HTTP_202_ACCEPTED)
def reshape_project_request(project_id: int, session: SessionDep) -> JobOut:
    """Ponovo izmeri oblike oblačića iz očišćenih strana (slike se ne diraju)."""
    get_project(session, project_id)
    job = Job(type="reshape_project", project_id=project_id, payload={"project_id": project_id})
    session.add(job)
    session.commit()
    return job


@router.post("/projects/{project_id}/clean", status_code=status.HTTP_202_ACCEPTED)
def clean_project_request(project_id: int, session: SessionDep) -> JobOut:
    """Očisti sve stranice sa blokovima (postojeća očišćena slika se pravi iznova)."""
    get_project(session, project_id)
    job = Job(type="clean_project", project_id=project_id, payload={"project_id": project_id})
    session.add(job)
    session.commit()
    return job


@router.post("/projects/{project_id}/prepare", status_code=status.HTTP_202_ACCEPTED)
def prepare_project_request(
    project_id: int, session: SessionDep, settings: SettingsDep, data: PrepareRequest | None = None
) -> JobOut:
    """Ceo album: OCR stranica bez blokova, prevod bez prevoda, čišćenje; urađeno se preskače."""
    get_project(session, project_id)
    data = data or PrepareRequest()
    job = Job(
        type="prepare_project",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "ocr_model": data.ocr_model or settings.ocr_model,
            "translation_model": data.translation_model or settings.translation_model,
        },
    )
    session.add(job)
    session.commit()
    return job
