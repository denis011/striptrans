from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from llama_mock import ocr_server, ollama_server

from app.config import OLLAMA_URL
from app.main import create_app
from app.models import WorkerHeartbeat, utcnow
from app.services.llamaserver import ocr_client
from app.services.llm_base import LlmError


def add_heartbeat(client, age_seconds: float = 0) -> None:
    with client.app.state.session_factory() as session:
        last_seen = utcnow() - timedelta(seconds=age_seconds)
        session.add(WorkerHeartbeat(worker_id="w1", last_seen=last_seen))
        session.commit()


def test_ping(client):
    assert client.get("/api/ping").json() == {"pong": True}


def test_health_ok_when_everything_is_up(client):
    add_heartbeat(client)

    body = client.get("/api/health").json()

    assert body["status"] == "ok"
    assert body["database"] == {"ok": True}
    assert body["worker"]["ok"] is True
    llama = body["llama_server"]
    assert (llama["ok"], llama["version"], llama["model"]) == (True, "b11189-abc", "qwen2.5vl:7b")
    assert [(m["name"], m["file"]) for m in llama["models"]] == [
        ("qwen2.5vl:7b", "Qwen2.5-VL-7B-Q4_K_M.gguf")
    ]


def test_health_degraded_without_worker_heartbeat(client):
    body = client.get("/api/health").json()

    assert body["status"] == "degraded"
    assert body["worker"] == {"ok": False, "last_seen": None}


def test_health_marks_stale_heartbeat_as_down(client):
    add_heartbeat(client, age_seconds=60)

    body = client.get("/api/health").json()

    assert body["worker"]["ok"] is False
    assert body["worker"]["last_seen"] is not None


def test_health_reports_llama_server_unreachable(client_llama_down):
    response = client_llama_down.get("/api/health")

    assert response.status_code == 200
    llama = response.json()["llama_server"]
    assert llama["ok"] is False
    assert "Connection refused" in llama["error"]


def test_debug_llm_returns_response_and_speed(client):
    response = client.post("/api/debug/llm", json={"prompt": "Non abbiamo tempo adesso."})

    assert response.status_code == 200
    assert response.json() == {
        "response": "Nemamo vremena sada.",
        "model": "qwen2.5vl:7b",
        "load_seconds": 0.0,
        "prompt_tokens_per_second": 160.0,
        "eval_tokens_per_second": 59.0,
        "truncated": False,
    }


def test_debug_llm_returns_502_when_llama_server_is_down(client_llama_down):
    response = client_llama_down.post("/api/debug/llm", json={"prompt": "ciao"})

    assert response.status_code == 502


def test_debug_llm_rejects_empty_prompt(client):
    assert client.post("/api/debug/llm", json={"prompt": ""}).status_code == 422


def test_ollama_is_an_alternative_ocr_server(settings):
    settings.ocr_server = "ollama"
    for installed, ok in ((("qwen2.5vl:7b", "gemma3:12b"), True), (("gemma3:12b",), False)):
        app = create_app(
            settings, llama_transport=httpx.MockTransport(ollama_server([], installed))
        )
        with TestClient(app) as client:
            llama = client.get("/api/health").json()["llama_server"]
            assert (llama["ok"], llama["server"]) == (ok, "ollama")
            if ok:
                assert llama["version"] == "Ollama 0.34.4"
                assert llama["models"][0]["file"] == "qwen2.5vl:7b"
            else:
                assert "nije instaliran" in llama["error"]


def test_auto_uses_llama_server_and_falls_back_to_ollama(settings):
    """Ugašen llama-server: posao prelazi na Ollamu bez restarta; upaljen opet ima prednost."""
    llama_up = {"value": True}
    ollama = ollama_server([])
    llama = ocr_server([])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.port == 8081:
            if not llama_up["value"]:
                raise httpx.ConnectError("Connection refused", request=request)
            return llama(request)
        return ollama(request)

    client = ocr_client(settings, httpx.MockTransport(handler))
    assert settings.ocr_server == "auto" and client.server == "llama-server"

    llama_up["value"] = False
    with pytest.raises(LlmError):
        client.generate("x", "qwen2.5vl:7b")  # prekid usred rada: posao čeka u redu
    assert client.generate("x", "qwen2.5vl:7b").response == "SCERIFFO!"
    assert client.server == "ollama"


def test_fixed_server_setting_is_respected(settings):
    settings.ocr_server = "llama-server"
    assert ocr_client(settings).server == "llama-server"
    settings.ocr_server = "ollama"
    only = ocr_client(settings)
    assert (only.server, only.base_url) == ("ollama", OLLAMA_URL)
