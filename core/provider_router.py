"""Explicit, bounded provider selection and zero-price-safe failover routing."""
from __future__ import annotations

from core.fallback_chat_client import FallbackChatClient
from core.google_chat_client import GoogleChatClient
from core.groq_chat_client import GroqChatClient
from core.ollama_client import OllamaClient
from core.openrouter_free_client import OpenRouterFreeClient
from core.trained_lora_client import TRAINED_LORA_LABEL, TrainedLoraClient

GROQ_MODEL = "openai/gpt-oss-120b"
GOOGLE_MODEL = "gemini-3.6-flash"
OPENROUTER_FREE_MODEL = "openrouter/free"
LOCAL_PREFIX = "Ollama (Yerel): "
OPENROUTER_LABEL = "OpenRouter ücretsiz model havuzu (50 istek/gün sınırı)"


def fallback_options(selected: str, credentials: dict[str, str],
                     local_models: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """List only local inference or an API explicitly pinned to free models.

    Groq/Gemini are deliberately excluded as automatic fallbacks because this
    app cannot inspect whether an account has a paid billing tier enabled.
    """
    options = [f"Yerel Ollama · {name}" for name in local_models
               if f"{LOCAL_PREFIX}{name}" != selected]
    if credentials.get("OPENROUTER_API_KEY") and selected != OPENROUTER_LABEL:
        options.append(OPENROUTER_LABEL)
    return tuple(options)


def build_provider_router(
    selected: str,
    credentials: dict[str, str],
    local_models: list[str] | tuple[str, ...] = (),
    *,
    ollama_url: str = "http://127.0.0.1:11434",
    allow_fallback: bool = False,
    google_model: str = GOOGLE_MODEL,
    groq_model: str = GROQ_MODEL,
) -> FallbackChatClient:
    """Build a fresh per-turn router. External failover requires explicit opt-in."""
    local_models = tuple(model for model in local_models if isinstance(model, str) and model)
    if selected.startswith(LOCAL_PREFIX):
        primary_model = selected.removeprefix(LOCAL_PREFIX)
        if primary_model not in local_models:
            raise ValueError("Selected Ollama model is not available")
        primary = OllamaClient(ollama_url, timeout=180, max_output_tokens=1200,
                               think=False)
        primary_provider = "Ollama (Yerel)"
    elif selected == TRAINED_LORA_LABEL:
        primary = TrainedLoraClient(timeout=240)
        primary_model = primary.last_model_used
        primary_provider = TRAINED_LORA_LABEL
    elif selected.startswith("Groq"):
        key = credentials.get("GROQ_API_KEY")
        if not key:
            raise ValueError("Groq is not configured")
        primary_model = groq_model
        primary = GroqChatClient(key, timeout=25)
        primary_provider = "Groq"
    elif selected.startswith("Google Gemini"):
        key = credentials.get("GOOGLE_API_KEY")
        if not key:
            raise ValueError("Google Gemini is not configured")
        primary_model = google_model
        primary = GoogleChatClient(key, timeout=25)
        primary_provider = "Google Gemini"
    elif selected == OPENROUTER_LABEL:
        key = credentials.get("OPENROUTER_API_KEY")
        if not key:
            raise ValueError("OpenRouter is not configured")
        primary_model = OPENROUTER_FREE_MODEL
        primary = OpenRouterFreeClient(key, timeout=25)
        primary_provider = OPENROUTER_LABEL
    else:
        raise ValueError("Unknown or unavailable provider")

    chain: list[tuple[str, object, str]] = []
    for model_name in local_models:
        if f"{LOCAL_PREFIX}{model_name}" == selected:
            continue
        chain.append(("Ollama (Yerel)", OllamaClient(
            ollama_url, timeout=180, max_output_tokens=1200, think=False
        ), model_name))
    if credentials.get("OPENROUTER_API_KEY") and selected != OPENROUTER_LABEL:
        chain.append((OPENROUTER_LABEL,
                      OpenRouterFreeClient(credentials["OPENROUTER_API_KEY"], timeout=25),
                      OPENROUTER_FREE_MODEL))

    return FallbackChatClient(
        primary,
        fallback_chain=chain,
        allow_fallback=bool(allow_fallback and chain),
        primary_provider=primary_provider,
    )

