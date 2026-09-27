"""Worker: uzima poslove iz tabele jobs i javlja da je živ (heartbeat)."""

import logging
import signal
import socket
import time
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings
from app.db import make_engine
from app.jobs import (
    HANDLERS,
    RESUMABLE_JOBS,
    JobCancelled,
    JobContext,
    beat,
    recover_interrupted_jobs,
)
from app.models import Job, utcnow
from app.services.llamaserver import LlamaServerClient, ocr_client
from app.services.llm_base import LlmError

log = logging.getLogger("worker")


def claim_job(session: Session) -> Job | None:
    job_id = session.scalar(select(Job.id).where(Job.status == "queued").order_by(Job.id).limit(1))
    if job_id is None:
        return None
    claimed = session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "queued")
        .values(status="running", updated_at=utcnow())
    )
    session.commit()
    if claimed.rowcount != 1:
        return None
    return session.get(Job, job_id)


def can_wait(job: Job, exc: Exception) -> bool:
    """llama-server (ili OpenRouter) nije dostupan, a posao se može nastaviti gde je stao.

    Takav posao se vraća u red umesto da propadne: kad se llama-server restartuje ili još učitava
    model, ceo red ne sme da propadne za par sekundi.
    """
    unreachable = isinstance(exc, LlmError) and exc.status is None
    return unreachable and job.type in RESUMABLE_JOBS and not (job.payload or {}).get("replace")


def run_job(
    session: Session, job: Job, settings: Settings, worker_id: str, llama: LlamaServerClient
) -> bool:
    """Izvrši posao; vraća True ako je posao vraćen u red jer model nije dostupan."""
    handler = HANDLERS.get(job.type)
    requeued = False
    try:
        if handler is None:
            raise ValueError(f"nepoznat tip posla: {job.type}")
        job.result = handler(JobContext(session, settings, job, worker_id, llama))
        job.status = "done"
    except JobCancelled:
        session.rollback()
        log.info("posao %s je prekinut", job.id)
        job.status = "cancelled"
    except Exception as exc:
        session.rollback()
        if can_wait(job, exc):
            log.warning("posao %s čeka: %s", job.id, exc)
            job.status = "queued"
            requeued = True
        else:
            log.exception("posao %s nije uspeo", job.id)
            job.status = "failed"
            job.error = str(exc)
    session.commit()
    return requeued


def new_client(settings: Settings) -> LlamaServerClient:
    return ocr_client(settings)


def run_once(
    session_factory: sessionmaker,
    worker_id: str,
    settings: Settings,
    llama: LlamaServerClient | None = None,
) -> bool:
    """Javi heartbeat i obradi najviše jedan posao. Vraća True ako je posao obrađen.

    Posao vraćen u red jer model nije dostupan nije obrađen: worker tada pravi pauzu
    `worker_retry_interval` pre sledećeg pokušaja.
    """
    with session_factory() as session:
        beat(session, worker_id)
        job = claim_job(session)
        if job is None:
            return False
        log.info("posao %s (%s) počinje", job.id, job.type)
        client = llama or new_client(settings)
        try:
            requeued = run_job(session, job, settings, worker_id, client)
        finally:
            if llama is None:
                client.close()
    if requeued:
        time.sleep(settings.worker_retry_interval)
        return False
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    session_factory = sessionmaker(make_engine(settings.database_url))
    worker_id = socket.gethostname()
    llama = new_client(settings)

    stopping = False

    def stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    with session_factory() as session:
        if recovered := recover_interrupted_jobs(session, Path(settings.data_dir)):
            log.warning("obrađeno %s poslova prekinutih restartom", recovered)

    log.info("worker %s pokrenut", worker_id)
    while not stopping:
        if not run_once(session_factory, worker_id, settings, llama):
            time.sleep(settings.worker_poll_interval)
    log.info("worker %s zaustavljen", worker_id)


if __name__ == "__main__":
    main()
