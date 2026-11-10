"""Bounded chat-provider failover with explicit external-call consent."""
from __future__ import annotations

from typing import Protocol

from core.safety_policy import safe_response_for_prompt

from core.provider_failure import copy_safe_failure_metadata


class ChatClient(Protocol):
    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str: ...



class FallbackChatClient:
    """Use a primary client until it fails, then pin the run to one fallback.

    External fallback is disabled by default. Each wrapped client must enforce
    its own request timeout; this class never retries a model call.
    """

    def __init__(
        self,
        primary: ChatClient,
        *,
        fallback: ChatClient | None = None,
        fallback_model: str | None = None,
        fallback_provider: str = "fallback",
        fallback_chain: list[tuple[str, ChatClient, str]] | None = None,
        allow_fallback: bool = False,
        primary_provider: str = "primary",
    ) -> None:
        chain = list(fallback_chain or [])
        if fallback is not None or fallback_model is not None:
            if fallback is None or not fallback_model:
                raise ValueError("A fallback requires both a client and model")
            chain.insert(0, (fallback_provider, fallback, fallback_model))
        if allow_fallback and not chain:
            raise ValueError("An enabled fallback requires at least one client and model")
        if any(not provider or not model for provider, _, model in chain):
            raise ValueError("Each fallback requires a provider name and model")
        self.primary = primary
        if not primary_provider:
            raise ValueError("Primary provider name is required")
        self.primary_provider = primary_provider
        self.fallback_chain = chain
        self.allow_fallback = allow_fallback
        self.fallback_active = False
        self.last_model_used: str | None = None
        self.last_provider_used: str | None = None
        self.fallback_reason: str | None = None
        self._next_fallback = 0
        self._active_fallback: tuple[str, ChatClient, str] | None = None
        self._failure_kinds: list[str] = []

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        safe_response = safe_response_for_prompt(prompt)
        if safe_response is not None:
            self.last_model_used = "deterministic-policy"
            self.last_provider_used = "CANO Safety Gate"
            return safe_response
        if self.fallback_active:
            if self._active_fallback is not None:
                provider, client, model_name = self._active_fallback
                try:
                    result = client.chat(model_name, system, prompt, temperature=temperature)
                    self.last_model_used = getattr(client, "last_model_used", None) or model_name
                    self.last_provider_used = provider
                    return result
                except Exception as exc:
                    self._failure_kinds.append(type(exc).__name__)
                    self._active_fallback = None
            return self._call_next_fallback(system, prompt, temperature)
        try:
            result = self.primary.chat(model, system, prompt, temperature=temperature)
            self.last_model_used = getattr(self.primary, "last_model_used", None) or model
            self.last_provider_used = self.primary_provider
            return result
        except Exception as exc:
            if not self.allow_fallback:
                failure = RuntimeError(
                    f"Primary chat provider failed ({type(exc).__name__}); external fallback is disabled"
                )
                copy_safe_failure_metadata(exc, failure)
                raise failure from None
            self.fallback_active = True
            self.fallback_reason = type(exc).__name__
            self._failure_kinds.append(type(exc).__name__)
            return self._call_next_fallback(system, prompt, temperature)

    def _call_next_fallback(self, system: str, prompt: str, temperature: float) -> str:
        self.last_model_used = None
        self.last_provider_used = None
        while self._next_fallback < len(self.fallback_chain):
            provider, client, model_name = self.fallback_chain[self._next_fallback]
            self._next_fallback += 1
            try:
                result = client.chat(model_name, system, prompt, temperature=temperature)
            except Exception as exc:
                self._failure_kinds.append(type(exc).__name__)
                continue
            self._active_fallback = (provider, client, model_name)
            self.last_model_used = getattr(client, "last_model_used", None) or model_name
            self.last_provider_used = provider
            return result
        failures = ", ".join(self._failure_kinds) or "no fallback configured"
        raise RuntimeError(f"All explicitly enabled chat providers failed ({failures})") from None

