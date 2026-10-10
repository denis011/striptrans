"""OpenRouter: udaljeni modeli za prevod, isti interfejs kao LlamaServerClient (`generate`)."""

import base64
import json
import re

import httpx

from app.services.llm_base import GenerateResult, LlmError

PREFIX = "or:"  # ime modela sa ovim prefiksom ide na OpenRouter (or:anthropic/claude-sonnet-5)
FENCE = re.compile(r"^```[a-z]*\s*|\s*```$")


class OpenRouterError(LlmError):
    """Status None: OpenRouter nije dostupan, posao čeka u redu."""


def _body_error(error: object) -> OpenRouterError:
    """Greška provajdera u telu odgovora; bez statusa bi posao zauvek čekao u redu."""
    code = error.get("code") if isinstance(error, dict) else None
    status = code if isinstance(code, int) else 502
    return OpenRouterError(f"OpenRouter: {json.dumps(error)[:300]}", status)


def is_remote(model: str) -> bool:
    return model.startswith(PREFIX)


def remote_name(model: str) -> str:
    return model.removeprefix(PREFIX)


class OpenRouterClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 180.0,
        transport: httpx.BaseTransport | None = None,
        reasoning: bool = True,
        provider_sort: str = "",
    ):
        self.base_url = base_url
        self.reasoning = reasoning  # prevod ne traži razmišljanje, a ono ume da utrostruči cenu
        self.provider_sort = provider_sort  # npr. "throughput": zaobiđi spore provajdere
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "X-Title": "StripTrans",
            },
        )
        self.prompt_tokens = 0
        self.completion_tokens = 0

    def close(self) -> None:
        self._http.close()

    def _post(self, body: dict) -> dict:
        try:
            response = self._http.post("/chat/completions", json=body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            text = exc.response.text
            if "reasoning" in body and "reasoning" in text.lower():
                # neki modeli (glm-5.3-flash) ne daju da se razmišljanje ugasi
                return self._post({k: v for k, v in body.items() if k != "reasoning"})
            status = exc.response.status_code
            raise OpenRouterError(f"OpenRouter {status}: {text[:300]}", status) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise OpenRouterError(f"OpenRouter nije dostupan ({self.base_url}): {exc}") from exc

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 200,
        images: list[bytes] | None = None,
        temperature: float | None = None,
        format: dict | None = None,
    ) -> GenerateResult:
        name = remote_name(model)
        body: dict = {
            "model": name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        if not self.reasoning:
            body["reasoning"] = {"enabled": False}
        if self.provider_sort:
            body["provider"] = {"sort": self.provider_sort}
        if format is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "translations", "strict": True, "schema": format},
            }
        data = self._post(body)
        if "error" in data:  # OpenRouter greške provajdera stižu sa statusom 200
            raise _body_error(data["error"])
        usage = data.get("usage") or {}
        self.prompt_tokens += usage.get("prompt_tokens", 0)
        self.completion_tokens += usage.get("completion_tokens", 0)
        choices = data.get("choices") or [{}]
        content = (choices[0].get("message") or {}).get("content") or ""
        return GenerateResult(
            response=FENCE.sub("", content.strip()),
            model=data.get("model", name),
            load_seconds=0.0,
            prompt_tokens_per_second=0.0,
            eval_tokens_per_second=0.0,
            truncated=choices[0].get("finish_reason") == "length",
        )

    def edit_image(self, prompt: str, image: bytes, model: str) -> tuple[bytes, float | None]:
        """Model za slike (Gemini „image"): isečak + uputstvo → izmenjena slika i cena ($)."""
        body = {
            "model": remote_name(model),
            "modalities": ["image", "text"],
            "usage": {"include": True},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64," + base64.b64encode(image).decode()
                            },
                        },
                    ],
                }
            ],
        }
        data = self._post(body)
        if "error" in data:
            raise _body_error(data["error"])
        message = ((data.get("choices") or [{}])[0].get("message")) or {}
        images = message.get("images") or []
        if not images:
            raise OpenRouterError(
                f"model nije vratio sliku: {(message.get('content') or '')[:200]}", 502
            )
        url = images[0]["image_url"]["url"]
        return base64.b64decode(url.split(",", 1)[1]), (data.get("usage") or {}).get("cost")
