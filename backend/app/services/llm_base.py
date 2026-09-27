"""Zajedničko za klijente modela (llama-server za OCR, OpenRouter za prevod)."""

from dataclasses import dataclass


class LlmError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status  # HTTP status odgovora; None: server nije dostupan ili nije spreman

    @property
    def model_failed(self) -> bool:
        """Model nije uspeo na ovom ulazu (npr. zavrteo se u krug), a server radi."""
        return self.status is not None and self.status >= 500


@dataclass
class GenerateResult:
    response: str
    model: str
    load_seconds: float
    prompt_tokens_per_second: float
    eval_tokens_per_second: float
    truncated: bool = False  # odgovor je prekinut na max_tokens (finish_reason „length")
