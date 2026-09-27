from datetime import UTC, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.deps import LlamaDep, SessionDep, SettingsDep
from app.models import WorkerHeartbeat, utcnow
from app.services.llm_base import LlmError

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/ping")
def ping() -> dict:
    return {"pong": True}


@router.get("/health")
def health(session: SessionDep, llama: LlamaDep, settings: SettingsDep) -> dict:
    database: dict = {"ok": True}
    worker: dict = {"ok": False, "last_seen": None}
    try:
        session.execute(text("SELECT 1"))
        last_seen = session.scalar(select(func.max(WorkerHeartbeat.last_seen)))
    except SQLAlchemyError as exc:
        database = {"ok": False, "error": str(exc)}
    else:
        if last_seen is not None:
            worker = {
                "ok": utcnow() - last_seen < timedelta(seconds=settings.worker_heartbeat_timeout),
                "last_seen": last_seen.replace(tzinfo=UTC).isoformat(),
            }

    llama_status: dict = {"ok": False, "model": settings.ocr_model}
    try:
        models = llama.models()
        llama_status.update(ok=True, models=models, version=llama.version())
        if not models:  # Ollama radi, ali nema model
            llama_status.update(ok=False, error=f"model {settings.ocr_model} nije instaliran")
    except LlmError as exc:
        llama_status["error"] = str(exc)
    llama_status.update(server=llama.server, url=llama.base_url)  # automatski režim: koji radi

    ok = database["ok"] and worker["ok"] and llama_status["ok"]
    return {
        "status": "ok" if ok else "degraded",
        "database": database,
        "worker": worker,
        "llama_server": llama_status,
    }
