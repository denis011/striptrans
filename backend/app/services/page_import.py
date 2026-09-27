"""Posao uvoza: od uploadovanih fajlova pravi stranice projekta."""

import shutil
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Job, Page, Project
from app.services.importer import ImportFailed, PreparedPage, collect_sources, prepare_page

if TYPE_CHECKING:
    from app.jobs import JobContext

MAX_UPLOAD_BYTES = 2 * 1024**3
COPY_CHUNK = 1024 * 1024


def queue_import(
    session: Session,
    data_dir: str,
    project_id: int,
    kind: str,
    files: Iterable[tuple[str, BinaryIO]],
) -> Job:
    """Snimi uploadovane fajlove pod bezbednim imenima i napravi posao uvoza."""
    relative = Path("uploads", uuid.uuid4().hex)
    upload = Path(data_dir) / relative
    upload.mkdir(parents=True)
    entries = []
    total = 0
    try:
        for index, (name, stream) in enumerate(files):
            with (upload / str(index)).open("wb") as target:
                shutil.copyfileobj(stream, target, COPY_CHUNK)
                total += target.tell()
            if total > MAX_UPLOAD_BYTES:
                raise ImportFailed(f"upload je prevelik (najviše {MAX_UPLOAD_BYTES // 1024**3} GB)")
            entries.append({"name": name or f"fajl-{index + 1}", "stored_name": str(index)})
    except BaseException:
        shutil.rmtree(upload, ignore_errors=True)
        raise
    job = Job(
        type="import",
        project_id=project_id,
        payload={
            "project_id": project_id,
            "kind": kind,
            "upload_dir": str(relative),
            "files": entries,
        },
    )
    session.add(job)
    session.commit()
    return job


def delete_page_files(data_dir: Path, page: Page) -> None:
    for relative in (page.image_path, page.thumbnail_path, page.clean_path, page.mask_path):
        if relative:
            (data_dir / relative).unlink(missing_ok=True)


def cleanup_import(session: Session, data_dir: Path, job_id: int) -> None:
    """Obriši stranice i fajlove koje je napravio (neuspeli) posao uvoza."""
    for page in session.scalars(select(Page).where(Page.import_job_id == job_id)):
        delete_page_files(data_dir, page)
        session.delete(page)
    session.commit()


def _save_page(
    data_dir: Path, job: Job, kind: str, position: int, import_order: int, prepared: PreparedPage
) -> Page:
    project_id = job.payload["project_id"]
    stem = uuid.uuid4().hex
    image_path = Path("projects", str(project_id), kind, stem + prepared.extension)
    thumbnail_path = Path("projects", str(project_id), "thumbs", stem + ".webp")
    for relative, content in ((image_path, prepared.data), (thumbnail_path, prepared.thumbnail)):
        target = data_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return Page(
        project_id=project_id,
        kind=kind,
        position=position,
        import_order=import_order,
        source_name=prepared.source_name[-500:],
        width=prepared.width,
        height=prepared.height,
        image_path=str(image_path),
        thumbnail_path=str(thumbnail_path),
        import_job_id=job.id,
    )


def run_import(ctx: "JobContext") -> dict:
    session, job = ctx.session, ctx.job
    job_id = job.id
    payload = job.payload
    project_id, kind = payload["project_id"], payload["kind"]
    data_dir = Path(ctx.settings.data_dir)
    upload = data_dir / payload["upload_dir"]
    try:
        if session.get(Project, project_id) is None:
            raise ImportFailed("projekat ne postoji")
        sources = collect_sources((upload / f["stored_name"], f["name"]) for f in payload["files"])
        ctx.report(0, len(sources))
        position, import_order = session.execute(
            select(
                func.coalesce(func.max(Page.position), 0),
                func.coalesce(func.max(Page.import_order), 0),
            ).where(Page.project_id == project_id, Page.kind == kind)
        ).one()
        pages, skipped = 0, []
        for index, (name, data) in enumerate(sources, start=1):
            prepared = prepare_page(name, data)
            if prepared is None:
                skipped.append(name)
            else:
                position += 1
                import_order += 1
                pages += 1
                session.add(_save_page(data_dir, job, kind, position, import_order, prepared))
            ctx.report(index)
        if pages == 0:
            raise ImportFailed("nije pronađena nijedna slika")
        return {"pages": pages, "skipped": skipped}
    except Exception:
        session.rollback()
        cleanup_import(session, data_dir, job_id)
        raise
    finally:
        shutil.rmtree(upload, ignore_errors=True)
