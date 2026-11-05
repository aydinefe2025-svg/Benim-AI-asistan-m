"""Bounded chat-provider failover with explicit external-call consent."""
from __future__ import annotations

from typing import Protocol


class ChatClient(Protocol):
    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str: ...


class FallbackChatClient:
    """Use a primary client until it fails, then pin the run to one fallback.

    External fallback is disabled by default. Each wrapped client must enforce
    its own request timeout; this class never retries a model call.
    """

    def __init__(self, primary: ChatClient, *, fallback: ChatClient | None = None,
                 fallback_model: str | None = None, allow_fallback: bool = False) -> None:
        if allow_fallback and (fallback is None or not fallback_model):
            raise ValueError("An enabled fallback requires a client and model")
        self.primary = primary
        self.fallback = fallback
        self.fallback_model = fallback_model
        self.allow_fallback = allow_fallback
        self.fallback_active = False
        self.last_model_used: str | None = None
        self.fallback_reason: str | None = None

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        if self.fallback_active:
            return self._call_fallback(system, prompt, temperature)
        try:
            result = self.primary.chat(model, system, prompt, temperature=temperature)
            self.last_model_used = model
            return result
        except Exception as exc:
            if not self.allow_fallback:
                raise RuntimeError(
                    f"Primary chat provider failed ({type(exc).__name__}); external fallback is disabled"
                ) from None
            self.fallback_active = True
            self.fallback_reason = type(exc).__name__
            return self._call_fallback(system, prompt, temperature)

    def _call_fallback(self, system: str, prompt: str, temperature: float) -> str:
        assert self.fallback is not None and self.fallback_model is not None
        try:
            result = self.fallback.chat(
                self.fallback_model, system, prompt, temperature=temperature
            )
        except Exception as exc:
            raise RuntimeError(
                f"Primary and fallback chat providers failed ({type(exc).__name__})"
            ) from None
        self.last_model_used = self.fallback_model
        return result
