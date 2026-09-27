"""Lažni llama-server za testove (OpenAI API: /v1/chat/completions)."""

import base64
import json

import httpx

from app.services.llamaserver import LlamaServerClient

CHAT = "/v1/chat/completions"
MODEL = "qwen2.5vl:7b"


def reply(content: str, timings: dict | None = None, finish: str = "stop") -> httpx.Response:
    choice = {"message": {"content": content}, "finish_reason": finish}
    return httpx.Response(200, json={"choices": [choice], "timings": timings or {}})


def sent(request: httpx.Request) -> dict:
    """Telo zahteva uz izdvojeno uputstvo i slike."""
    body = json.loads(request.content)
    content = body["messages"][0]["content"]
    body["prompt"] = next(part["text"] for part in content if part["type"] == "text")
    body["images"] = [
        base64.b64decode(part["image_url"]["url"].split(",", 1)[1])
        for part in content
        if part["type"] == "image_url"
    ]
    return body


def refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("Connection refused", request=request)


def llama_client(handler) -> LlamaServerClient:
    return LlamaServerClient("http://llama", MODEL, transport=httpx.MockTransport(handler))


def ocr_server(requests: list, response: str = "```\nSCERIFFO!\n```"):
    """Server koji na svaki OCR zahtev vraća isti odgovor i pamti poslate zahteve."""

    def handler(request: httpx.Request) -> httpx.Response:
        match request.url.path:
            case "/health":
                return httpx.Response(200, json={"status": "ok"})
            case "/v1/models":
                return httpx.Response(200, json={"data": [{"id": "Qwen2.5-VL-7B-Q4_K_M.gguf"}]})
            case "/props":
                return httpx.Response(200, json={"build_info": "b11189-abc"})
            case "/v1/chat/completions":
                requests.append(sent(request))
                return reply(response, {"prompt_per_second": 160.04, "predicted_per_second": 59})
        return httpx.Response(404)

    return handler


def ollama_server(requests: list, installed=("qwen2.5vl:7b", "gemma3:12b"), response="SCERIFFO!"):
    """Ollama (OpenAI API): nema /health ni /props, /v1/models daje sve instalirane modele."""

    def handler(request: httpx.Request) -> httpx.Response:
        match request.url.path:
            case "/api/version":
                return httpx.Response(200, json={"version": "0.34.4"})
            case "/v1/models":
                return httpx.Response(200, json={"data": [{"id": name} for name in installed]})
            case "/v1/chat/completions":
                requests.append(sent(request))
                return reply(response)
        return httpx.Response(404, text="404 page not found")

    return handler
