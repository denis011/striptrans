from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings

OLLAMA_URL = "http://host.docker.internal:11434"


class Settings(BaseSettings):
    data_dir: str = "/data"
    models_dir: str = "/models"
    database_url: str = "sqlite:////data/striptrans.db"
    # OCR: llama-server (brži, docs/benchmarks/ocr-llamaserver.md) ili Ollama, oba OpenAI API
    # auto: llama-server ako odgovara, inače Ollama (proverava se pri radu, bez restarta)
    ocr_server: Literal["auto", "llama-server", "ollama"] = "auto"
    llama_server_url: str = "http://host.docker.internal:8081"
    ollama_url: str = OLLAMA_URL
    llama_server_timeout: float = 300.0
    ocr_model: str = "qwen2.5vl:7b"  # ime modela (Ollama ga traži; llama-server drži samo jedan)
    ocr_max_tokens: int = 400
    detector_model: str = "detector.onnx"
    sfx_detection: bool = True
    emphasis_detection: bool = (
        True  # naglasak iz originala posle OCR-a (docs/benchmarks/naglasak.md)
    )
    glossary_model: str = "or:google/gemini-3.1-flash-lite"
    translation_model: str = "or:google/gemini-3.1-flash-lite"  # izbor posle merenja 3c
    # AI prepravka natpisa (docs/benchmarks/ai-natpisi.md): kvalitetno za naslove, jeftino za
    # onomatopeje
    ai_image_model: str = "or:google/gemini-3.1-flash-image"
    ai_image_cheap_model: str = "or:google/gemini-3.1-flash-lite-image"
    openrouter_url: str = "https://openrouter.ai/api/v1"
    openrouter_api_key: str = ""
    openrouter_timeout: float = 90.0
    openrouter_reasoning: bool = False
    openrouter_provider_sort: str = "throughput"
    openrouter_models: str = (
        "or:google/gemini-3.1-flash-lite,or:qwen/qwen3.7-plus,"
        "or:google/gemma-4-31b-it,or:anthropic/claude-sonnet-5"
    )
    app_url: str = "http://localhost:5173"  # adresa editora; scenario za lektora vodi na stranicu
    worker_poll_interval: float = 2.0
    worker_retry_interval: float = 30.0  # pauza pre ponovnog pokušaja kad llama-server ne odgovara
    worker_heartbeat_timeout: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
