"""Poslovi koje izvršava worker."""

import shutil
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Export, Job, Page, TextBlock, WorkerHeartbeat, utcnow
from app.services import ai_patch, llm
from app.services.cleaning import clean_page, remeasure_shapes
from app.services.exporting import pack
from app.services.glossary_suggest import suggest_from_projects
from app.services.llamaserver import LlamaServerClient
from app.services.page_import import cleanup_import, run_import
from app.services.page_processing import process_page, unread
from app.services.page_translation import translate_page


def beat(session: Session, worker_id: str) -> None:
    heartbeat = session.get(WorkerHeartbeat, worker_id)
    if heartbeat is None:
        session.add(WorkerHeartbeat(worker_id=worker_id))
    else:
        heartbeat.last_seen = utcnow()
    session.commit()


RESUMABLE_JOBS = (
    "process_page",
    "process_project",
    "translate_page",
    "translate_project",
    "clean_page",
    "clean_project",
    "reshape_project",
    "export",
    "prepare_project",
)


class JobCancelled(Exception):
    """Korisnik je zatražio prekid posla."""


@dataclass
class JobContext:
    session: Session
    settings: Settings
    job: Job
    worker_id: str
    llama: LlamaServerClient  # OCR; prevod ide preko OpenRouter-a (services/llm.py)

    def report(self, progress: int, total: int | None = None) -> None:
        """Upiši napredak posla; usput javlja heartbeat da dug posao ne izgleda kao pad workera."""
        self.job.progress = progress
        if total is not None:
            self.job.total = total
        beat(self.session, self.worker_id)

    def check_cancelled(self) -> None:
        self.session.refresh(self.job, ["cancel_requested"])
        if self.job.cancel_requested:
            raise JobCancelled


def ping(ctx: JobContext) -> dict:
    return {"pong": True, **ctx.job.payload}


def process_page_job(ctx: JobContext) -> dict:
    page = ctx.session.get(Page, ctx.job.payload["page_id"])
    if page is None:
        raise ValueError("stranica ne postoji")

    def on_block(done: int, total: int) -> None:
        ctx.check_cancelled()
        ctx.report(done, total)

    result = process_page(
        ctx.session, ctx.settings, ctx.llama, page, ctx.job.payload["model"], on_block=on_block
    )
    return asdict(result)


def process_project_job(ctx: JobContext) -> dict:
    payload = ctx.job.payload
    pages = ctx.session.scalars(
        select(Page)
        .where(Page.project_id == payload["project_id"], Page.kind == "original")
        .order_by(Page.position)
    ).all()
    totals = {"pages": 0, "blocks": 0, "needs_review": 0, "skipped": 0}
    ctx.report(0, len(pages))
    for index, page in enumerate(pages):
        ctx.check_cancelled()

        def on_block(done: int, total: int, index: int = index) -> None:
            ctx.check_cancelled()
            ctx.report(index)  # isti napredak, ali heartbeat da duga stranica ne izgleda kao pad

        result = process_page(
            ctx.session,
            ctx.settings,
            ctx.llama,
            page,
            payload["model"],
            payload["replace"],
            on_block,
        )
        totals["skipped" if result.skipped else "pages"] += 1
        totals["blocks"] += result.blocks
        totals["needs_review"] += result.needs_review
        ctx.report(index + 1)
    return totals


def translate_page_job(ctx: JobContext) -> dict:
    page = ctx.session.get(Page, ctx.job.payload["page_id"])
    if page is None:
        raise ValueError("stranica ne postoji")
    ctx.report(0, 1)
    result = translate_page(ctx.session, page, ctx.job.payload["model"])
    ctx.report(1)
    return asdict(result)


def translate_project_job(ctx: JobContext) -> dict:
    payload = ctx.job.payload
    pages = ctx.session.scalars(
        select(Page)
        .where(Page.project_id == payload["project_id"], Page.kind == "original")
        .order_by(Page.position)
    ).all()
    totals = {"pages": 0, "translated": 0, "from_memory": 0, "too_long": 0}
    ctx.report(0, len(pages))
    for index, page in enumerate(pages, start=1):
        ctx.check_cancelled()
        if not page.skip:
            result = translate_page(
                ctx.session, page, payload["model"], include_drafts=payload["replace"]
            )
            totals["pages"] += 1
            for key, value in asdict(result).items():
                totals[key] += value
        ctx.report(index)
    return totals


def clean_page_job(ctx: JobContext) -> dict:
    page = ctx.session.get(Page, ctx.job.payload["page_id"])
    if page is None:
        raise ValueError("stranica ne postoji")
    ctx.report(0, 1)
    result = clean_page(ctx.session, ctx.settings, page)
    ctx.report(1)
    return asdict(result)


def clean_project_job(ctx: JobContext) -> dict:
    """Očisti stranice sa blokovima; preskočene (naslovnica, reklame) ostaju netaknute."""
    pages = ctx.session.scalars(
        select(Page)
        .where(Page.project_id == ctx.job.payload["project_id"], Page.kind == "original")
        .order_by(Page.position)
    ).all()
    totals = {"pages": 0, "blocks": 0, "pixels": 0, "inpainted": 0}
    ctx.report(0, len(pages))
    for index, page in enumerate(pages, start=1):
        ctx.check_cancelled()
        if not page.skip and page.blocks:
            result = clean_page(ctx.session, ctx.settings, page)
            totals["pages"] += 1
            totals["blocks"] += result.blocks
            totals["pixels"] += result.pixels
            totals["inpainted"] += result.inpainted
        ctx.report(index)
    return totals


def reshape_project_job(ctx: JobContext) -> dict:
    """Ponovo izmeri oblike oblačića na očišćenim stranama (bez ponovnog čišćenja)."""
    pages = ctx.session.scalars(
        select(Page)
        .where(Page.project_id == ctx.job.payload["project_id"], Page.kind == "original")
        .order_by(Page.position)
    ).all()
    totals = {"pages": 0, "blocks": 0}
    ctx.report(0, len(pages))
    for index, page in enumerate(pages, start=1):
        ctx.check_cancelled()
        changed = remeasure_shapes(ctx.session, ctx.settings, page)
        if changed:
            totals["pages"] += 1
            totals["blocks"] += changed
        ctx.report(index)
    return totals


def export_job(ctx: JobContext) -> dict:
    export = ctx.session.get(Export, ctx.job.payload["export_id"])
    if export is None:
        raise ValueError("izvoz ne postoji")
    try:
        pack(
            ctx.session,
            ctx.settings.data_dir,
            export,
            report=lambda done, total: ctx.report(done, total),
        )
    except Exception as exc:
        ctx.session.rollback()
        export.status, export.error = "failed", str(exc)
        ctx.session.commit()
        raise
    return {"export_id": export.id, "pages": len(export.positions), "size": export.size}


def needs_cleaning(page: Page) -> bool:
    """Stranica sa blokovima koja nije očišćena ili su joj blokovi menjani posle čišćenja."""
    if page.skip or not page.blocks:
        return False
    if page.cleaned_at is None:
        return True
    return any(block.updated_at and block.updated_at > page.cleaned_at for block in page.blocks)


def prepare_project_job(ctx: JobContext) -> dict:
    """Ceo album u jednom poslu: detekcija i OCR → prevod → čišćenje; urađeno se preskače."""
    payload = ctx.job.payload
    pages = ctx.session.scalars(
        select(Page)
        .where(Page.project_id == payload["project_id"], Page.kind == "original")
        .order_by(Page.position)
    ).all()
    active = [page for page in pages if not page.skip]
    totals = {"ocr_pages": 0, "blocks": 0, "translated": 0, "from_memory": 0, "cleaned": 0}
    stages = (("OCR", "ocr"), ("prevod", "translate"), ("čišćenje", "clean"))
    total = len(active) * len(stages)
    ctx.report(0, total)
    done = 0
    for label, stage in stages:
        ctx.job.result = {"stage": label}
        for page in active:
            ctx.check_cancelled()
            if stage == "ocr" and (not page.blocks or any(map(unread, page.blocks))):

                def on_block(_done: int, _total: int, progress: int = done) -> None:
                    ctx.check_cancelled()
                    ctx.report(progress)

                result = process_page(
                    ctx.session,
                    ctx.settings,
                    ctx.llama,
                    page,
                    payload["ocr_model"],
                    False,
                    on_block,
                )
                totals["ocr_pages"] += not result.skipped
                totals["blocks"] += result.blocks
            elif stage == "translate":
                result = translate_page(
                    ctx.session,
                    page,
                    payload["translation_model"],
                    include_drafts=False,
                )
                totals["translated"] += result.translated
                totals["from_memory"] += result.from_memory
            elif stage == "clean" and needs_cleaning(page):
                clean_page(ctx.session, ctx.settings, page)
                totals["cleaned"] += 1
            done += 1
            ctx.report(done)
    return totals


def ai_patch_job(ctx: JobContext) -> dict:
    """AI prepravka natpisa: predlog slike za blok (posle restarta se ne ponavlja sam: plaća se)."""
    payload = ctx.job.payload
    block = ctx.session.get(TextBlock, payload["block_id"])
    if block is None:
        raise ValueError("blok ne postoji")
    page = ctx.session.get(Page, block.page_id)
    client = llm.remote_client(ctx.settings)
    return ai_patch.make_proposal(
        client, ctx.settings, page, block, payload.get("quality", "quality"), ctx.job.id
    )


HANDLERS: dict[str, Callable[[JobContext], dict]] = {
    "ping": ping,
    "import": run_import,
    "process_page": process_page_job,
    "process_project": process_project_job,
    "glossary_suggest": lambda ctx: suggest_from_projects(ctx),
    "translate_page": translate_page_job,
    "translate_project": translate_project_job,
    "clean_page": clean_page_job,
    "clean_project": clean_project_job,
    "reshape_project": reshape_project_job,
    "export": export_job,
    "prepare_project": prepare_project_job,
    "ai_patch": ai_patch_job,
}


def recover_interrupted_jobs(session: Session, data_dir: Path) -> int:
    """Posle restarta workera: ponovljive obrade vrati u red, ostale poslove označi kao neuspele."""
    jobs = session.scalars(select(Job).where(Job.status == "running")).all()
    for job in jobs:
        if job.type in RESUMABLE_JOBS and not job.payload.get("replace"):
            # stranica se obradi ponovo, a projekat preskače stranice koje su već obrađene
            job.status = "queued"
            job.progress = 0
            continue
        if job.type == "import":
            cleanup_import(session, data_dir, job.id)
            shutil.rmtree(data_dir / job.payload["upload_dir"], ignore_errors=True)
        job.status = "failed"
        job.error = "prekinuto restartovanjem workera"
    session.commit()
    return len(jobs)
