"""Klijent za prevod i glosar: samo OpenRouter (modeli sa prefiksom `or:`)."""

from app.config import Settings, get_settings
from app.services.openrouter import OpenRouterClient, OpenRouterError, is_remote

_remote: OpenRouterClient | None = None


def remote_client(settings: Settings | None = None) -> OpenRouterClient:
    """Jedan klijent po procesu, da bi se brojali potrošeni tokeni."""
    global _remote
    settings = settings or get_settings()
    if not settings.openrouter_api_key:
        # status: posao propada odmah umesto da čeka u redu na ključ koji neće stići
        raise OpenRouterError("OPENROUTER_API_KEY nije podešen (vidi .env)", 401)
    if _remote is None:
        _remote = OpenRouterClient(
            settings.openrouter_url,
            settings.openrouter_api_key,
            settings.openrouter_timeout,
            reasoning=settings.openrouter_reasoning,
            provider_sort=settings.openrouter_provider_sort,
        )
    return _remote


def translation_client(model: str, settings: Settings | None = None) -> OpenRouterClient:
    if not is_remote(model):
        raise OpenRouterError(
            f"model {model} nije podržan: prevod ide preko OpenRouter-a (or:…)", 400
        )
    return remote_client(settings)


def remote_models(settings: Settings | None = None) -> list[dict]:
    """Modeli sa OpenRouter-a ponuđeni u interfejsu (iz podešavanja)."""
    settings = settings or get_settings()
    if not settings.openrouter_api_key:
        return []
    names = [name.strip() for name in settings.openrouter_models.split(",") if name.strip()]
    return [
        {"name": name, "size": None, "capabilities": ["completion", "remote"]} for name in names
    ]
