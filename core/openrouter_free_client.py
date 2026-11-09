"""OpenRouter adapter pinned to its free-model router; never selects paid IDs."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class OpenRouterError(RuntimeError):
    """A sanitized OpenRouter failure without credentials or response bodies."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 failure_kind: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.failure_kind = failure_kind


class OpenRouterFreeClient:
    endpoint = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str, *, timeout: float = 25.0,
                 max_output_tokens: int = 1000) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("OpenRouter API key is required")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Timeout must be positive")
        if type(max_output_tokens) is not int or max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be a positive integer")
        self._api_key = api_key.strip()
        self.timeout = float(timeout)
        self.max_output_tokens = max_output_tokens
        self.last_model_used: str | None = None

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        # Ignore caller-supplied model names, including paid model IDs. This adapter
        # always uses OpenRouter's explicitly free model pool.
        if not isinstance(system, str) or not isinstance(prompt, str):
            raise ValueError("System and prompt must be strings")
        payload = json.dumps({
            "model": "openrouter/free",
            # Do not route prompts to providers that retain or train on them.
            # If no eligible free endpoint exists, fail closed instead.
            "provider": {"data_collection": "deny", "zdr": True},
            "messages": [
                {"role": "system", "content": system[:12000]},
                {"role": "user", "content": prompt[:30000]},
            ],
            "temperature": temperature,
            "max_tokens": self.max_output_tokens,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://cano.local",
                "X-Title": "CANO free provider pool",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request failed (HTTP {exc.code})",
                                  status_code=exc.code) from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeError) as exc:
            raise OpenRouterError(
                f"OpenRouter request failed ({type(exc).__name__})",
                failure_kind=("network" if isinstance(exc, (urllib.error.URLError, TimeoutError))
                              else "response" if isinstance(exc, (json.JSONDecodeError, UnicodeError))
                              else "unknown"),
            ) from None
        try:
            choice = result["choices"][0]
            content = choice["message"]["content"]
            model_used = result.get("model")
        except (KeyError, IndexError, TypeError):
            raise OpenRouterError("OpenRouter returned an invalid response", failure_kind="response") from None
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterError("OpenRouter returned no usable text", failure_kind="response")
        self.last_model_used = model_used if isinstance(model_used, str) else "openrouter/free"
        return content.strip()

