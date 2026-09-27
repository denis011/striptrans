"""Lažni OpenRouter za testove prevoda i glosara: odgovori redom, zahtevi se pamte."""

import json

import httpx

from app.services import llm
from app.services.openrouter import OpenRouterClient


def use_remote(monkeypatch, answers: list, requests: list) -> OpenRouterClient:
    """Prevod ide na ovaj klijent; svaki odgovor je JSON koji model „vraća"."""
    replies = iter(answers)

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        body["prompt"] = body["messages"][0]["content"]
        body["format"] = body.get("response_format", {}).get("json_schema", {}).get("schema")
        requests.append(body)
        content = json.dumps(next(replies))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = OpenRouterClient("https://or", "tajna", transport=httpx.MockTransport(handler))
    monkeypatch.setattr(llm, "remote_client", lambda settings=None: client)
    return client
