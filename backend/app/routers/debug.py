from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.deps import LlamaDep, SettingsDep
from app.services.llm_base import LlmError

router = APIRouter(prefix="/api/debug", tags=["debug"])


class LlmRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    model: str | None = None
    max_tokens: int = Field(default=200, ge=1, le=2000)


@router.post("/llm")
def debug_llm(request: LlmRequest, llama: LlamaDep, settings: SettingsDep) -> dict:
    """Kratak prompt kroz llama-server; brzina generisanja pokazuje da li model radi na GPU-u."""
    model = request.model or settings.ocr_model
    try:
        result = llama.generate(request.prompt, model, request.max_tokens)
    except LlmError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return asdict(result)
