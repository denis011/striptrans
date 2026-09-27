"""llama-server (llama.cpp) ili Ollama na Windows hostu: OCR vision modelom preko OpenAI API-ja.

llama-server drži jedan model i ime modela zanemaruje; Ollama bira model po imenu. Uz
`OCR_SERVER=auto` koristi se onaj koji odgovara (llama-server ima prednost, brži je).
"""

import base64
import time

import httpx

from app.config import Settings
from app.services.llm_base import GenerateResult, LlmError

STATUS_TIMEOUT = 3.0
NOT_FOUND = 404
NOT_READY = 503  # server se pokreće i učitava model: posao treba da sačeka, a ne da propadne


class LlamaServerClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 300.0,
        transport: httpx.BaseTransport | None = None,
        ollama: bool = False,
    ):
        self.base_url = base_url
        self.model = model
        self.ollama = ollama  # Ollama: /v1/models daje sve instalirane modele
        self.server = "ollama" if ollama else "llama-server"
        self._http = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._http.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"OCR server {status}: {exc.response.text[:300]}"
            raise LlmError(message, None if status == NOT_READY else status) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise LlmError(f"OCR server nije dostupan ({self.base_url}): {exc}") from exc

    def version(self) -> str:
        try:
            return self._request("GET", "/props", timeout=STATUS_TIMEOUT).get("build_info", "")
        except LlmError as exc:
            if exc.status != NOT_FOUND:
                raise
        # Ollama nema /props
        data = self._request("GET", "/api/version", timeout=STATUS_TIMEOUT)
        return f"Ollama {data.get('version', '')}".strip()

    def models(self) -> list[dict]:
        """Model iz podešavanja: kod llama-servera onaj koji drži (uz ime GGUF fajla), kod Ollame
        onaj sa tim imenom; ako ga Ollama nema, spisak je prazan."""
        try:
            self._request("GET", "/health", timeout=STATUS_TIMEOUT)  # 503 dok se model učitava
        except LlmError as exc:
            if exc.status != NOT_FOUND:  # Ollama nema /health
                raise
        data = self._request("GET", "/v1/models", timeout=STATUS_TIMEOUT).get("data") or []
        ids = [item.get("id") for item in data]
        if self.ollama:
            if self.model not in ids:
                return []
            file = self.model
        else:
            file = ids[0] if ids else None
        entry = {"name": self.model, "file": file, "size": None}
        return [entry | {"capabilities": self.capabilities(self.model)}]

    def capabilities(self, model: str) -> list[str]:
        return ["completion", "vision"]

    def generate(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 200,
        images: list[bytes] | None = None,
        temperature: float | None = None,
    ) -> GenerateResult:
        content: list[dict] = [
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()},
            }
            for image in images or []
        ]
        content.append({"type": "text", "text": prompt})
        body: dict = {
            "model": model,  # Ollama bira model po imenu; llama-server ga zanemaruje
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            body["temperature"] = temperature
        data = self._request("POST", "/v1/chat/completions", json=body)
        choices = data.get("choices") or [{}]
        timings = data.get("timings") or {}
        return GenerateResult(
            response=((choices[0].get("message") or {}).get("content") or "").strip(),
            model=model,
            load_seconds=0.0,
            prompt_tokens_per_second=round(timings.get("prompt_per_second", 0.0), 1),
            eval_tokens_per_second=round(timings.get("predicted_per_second", 0.0), 1),
        )


RECHECK = 60.0  # s: koliko dugo važi izbor servera u automatskom režimu


class AutoOcrClient:
    """Isti interfejs kao LlamaServerClient: radi sa serverom koji odgovara (llama-server ima
    prednost). Izbor se ponovo proverava posle RECHECK sekundi i kad server prestane da odgovara."""

    def __init__(self, llama: LlamaServerClient, ollama: LlamaServerClient):
        self.clients = (llama, ollama)
        self.model = llama.model
        self._active: LlamaServerClient | None = None
        self._checked = 0.0

    def _choose(self) -> LlamaServerClient:
        if self._active is not None and time.monotonic() - self._checked < RECHECK:
            return self._active
        llama, ollama = self.clients
        chosen = llama  # ako ne odgovara nijedan, greška dolazi od llama-servera
        try:
            llama._request("GET", "/health", timeout=STATUS_TIMEOUT)
        except LlmError as exc:
            # 503: llama-server radi i učitava model; 404: na toj adresi nije llama-server
            if exc.status != NOT_READY:
                try:
                    ollama._request("GET", "/api/version", timeout=STATUS_TIMEOUT)
                    chosen = ollama
                except LlmError:
                    pass
        self._active, self._checked = chosen, time.monotonic()
        return chosen

    def _call(self, name: str, *args, **kwargs):
        client = self._choose()
        try:
            return getattr(client, name)(*args, **kwargs)
        except LlmError as exc:
            if exc.status is None:
                self._active = None  # server ne odgovara: sledeći poziv ponovo bira
            raise

    @property
    def server(self) -> str:
        return self._choose().server

    @property
    def base_url(self) -> str:
        return self._choose().base_url

    def version(self) -> str:
        return self._call("version")

    def models(self) -> list[dict]:
        return self._call("models")

    def capabilities(self, model: str) -> list[str]:
        return ["completion", "vision"]

    def generate(self, *args, **kwargs) -> GenerateResult:
        return self._call("generate", *args, **kwargs)

    def close(self) -> None:
        for client in self.clients:
            client.close()


def ocr_client(
    settings: Settings, transport: httpx.BaseTransport | None = None
) -> LlamaServerClient | AutoOcrClient:
    """Klijent za OCR server iz podešavanja (llama-server, Ollama ili automatski izbor)."""

    def client(url: str, ollama: bool) -> LlamaServerClient:
        timeout = settings.llama_server_timeout
        return LlamaServerClient(url, settings.ocr_model, timeout, transport, ollama)

    llama = client(settings.llama_server_url, False)
    if settings.ocr_server == "llama-server":
        return llama
    ollama = client(settings.ollama_url, True)
    if settings.ocr_server == "ollama":
        llama.close()
        return ollama
    return AutoOcrClient(llama, ollama)
