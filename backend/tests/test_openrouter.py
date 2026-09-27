import json

import httpx
import pytest

from app.config import get_settings
from app.services import llm
from app.services.openrouter import OpenRouterClient, OpenRouterError
from app.services.translation import SCHEMA


def fake_client(reply: dict, requests: list, status: int = 200) -> OpenRouterClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, dict(request.headers), json.loads(request.content)))
        return httpx.Response(status, json=reply)

    return OpenRouterClient(
        "https://openrouter.ai/api/v1", "tajna", transport=httpx.MockTransport(handler)
    )


def test_request_drops_prefix_and_asks_for_json_schema():
    requests: list = []
    reply = {
        "model": "anthropic/claude-sonnet-5",
        "choices": [{"message": {"content": '```json\n{"translations": []}\n```'}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 250},
    }
    client = fake_client(reply, requests)

    result = client.generate(
        "prevedi", "or:anthropic/claude-sonnet-5", 2048, temperature=0.2, format=SCHEMA
    )

    path, headers, body = requests[0]
    assert path.endswith("/chat/completions")
    assert headers["authorization"] == "Bearer tajna"
    assert body["model"] == "anthropic/claude-sonnet-5"
    assert body["messages"] == [{"role": "user", "content": "prevedi"}]
    assert body["max_tokens"] == 2048 and body["temperature"] == 0.2
    assert body["response_format"]["json_schema"]["schema"] == SCHEMA
    assert result.response == '{"translations": []}'  # ograda oko koda je uklonjena
    assert (client.prompt_tokens, client.completion_tokens) == (1200, 250)


def test_provider_error_with_status_200_raises():
    client = fake_client({"error": {"message": "nema kredita", "code": 402}}, [])

    with pytest.raises(OpenRouterError, match="nema kredita"):
        client.generate("prevedi", "or:z-ai/glm-5.3")


def test_http_error_raises():
    client = fake_client({"detail": "no"}, [], status=401)

    with pytest.raises(OpenRouterError, match="401"):
        client.generate("prevedi", "or:z-ai/glm-5.3")


def test_translation_goes_only_to_openrouter(monkeypatch):
    llm._remote = None
    get_settings.cache_clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "tajna")

    with pytest.raises(OpenRouterError, match="OpenRouter") as error:
        llm.translation_client("gemma3:12b")
    assert error.value.status == 400  # posao propada, ne čeka u redu
    remote = llm.translation_client("or:anthropic/claude-sonnet-5")
    assert isinstance(remote, OpenRouterClient)
    assert llm.translation_client("or:z-ai/glm-5.3") is remote  # isti klijent broji tokene

    names = [model["name"] for model in llm.remote_models()]
    assert "or:anthropic/claude-sonnet-5" in names

    llm._remote = None
    get_settings.cache_clear()


def test_remote_without_key_is_an_error(monkeypatch):
    llm._remote = None
    get_settings.cache_clear()
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    with pytest.raises(OpenRouterError, match="OPENROUTER_API_KEY") as error:
        llm.translation_client("or:anthropic/claude-sonnet-5")
    assert error.value.status == 401
    assert llm.remote_models() == []

    get_settings.cache_clear()


def test_reasoning_can_be_switched_off():
    requests: list = []
    reply = {"choices": [{"message": {"content": "{}"}}]}

    def client(reasoning: bool) -> OpenRouterClient:
        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(json.loads(request.content))
            return httpx.Response(200, json=reply)

        return OpenRouterClient(
            "https://openrouter.ai/api/v1",
            "tajna",
            transport=httpx.MockTransport(handler),
            reasoning=reasoning,
        )

    client(True).generate("prevedi", "or:z-ai/glm-5.3")
    client(False).generate("prevedi", "or:z-ai/glm-5.3")

    assert "reasoning" not in requests[0]
    assert requests[1]["reasoning"] == {"enabled": False}


def test_provider_sort_is_sent_when_set():
    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    client = OpenRouterClient(
        "https://openrouter.ai/api/v1",
        "tajna",
        transport=httpx.MockTransport(handler),
        provider_sort="throughput",
    )
    client.generate("prevedi", "or:qwen/qwen3.7-plus")

    assert requests[0]["provider"] == {"sort": "throughput"}


def test_mandatory_reasoning_is_retried_with_reasoning_on():
    requests: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if "reasoning" in body:
            return httpx.Response(400, json={"error": {"message": "Reasoning is mandatory"}})
        return httpx.Response(
            200, json={"choices": [{"message": {"content": '{"translations": []}'}}]}
        )

    client = OpenRouterClient(
        "https://openrouter.ai/api/v1",
        "tajna",
        transport=httpx.MockTransport(handler),
        reasoning=False,
    )
    result = client.generate("prevedi", "or:z-ai/glm-5.3-flash")

    assert len(requests) == 2 and "reasoning" not in requests[1]
    assert result.response == '{"translations": []}'


def test_schemas_close_every_object_for_openai_strict_mode():
    """OpenAI odbija strogu šemu u kojoj neki objekat nema additionalProperties: false."""
    from app.services import glossary_suggest

    def objects(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                yield node
            for value in node.values():
                yield from objects(value)

    for schema in (SCHEMA, glossary_suggest.SCHEMA):
        assert all(item.get("additionalProperties") is False for item in objects(schema))
