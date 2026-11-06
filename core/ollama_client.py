"""Minimal Ollama HTTP client using only the Python standard library."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaError(RuntimeError):
    """Raised when Ollama is unreachable or returns an invalid response."""


class OllamaClient:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", timeout: int = 180,
                 max_output_tokens: int | None = None,
                 think: bool | None = None) -> None:
        if max_output_tokens is not None and (
            type(max_output_tokens) is not int or max_output_tokens <= 0
        ):
            raise ValueError("max_output_tokens must be a positive integer")
        if think is not None and type(think) is not bool:
            raise ValueError("think must be a boolean or None")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self.think = think

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data is not None else {},
            method="POST" if data is not None else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                decoded = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama HTTP {exc.code} at {path}: {body}") from exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise OllamaError(f"Ollama request failed at {path}: {exc}") from exc
        if not isinstance(decoded, dict):
            raise OllamaError(f"Ollama returned an unexpected response for {path}")
        return decoded

    def list_models(self) -> list[str]:
        response = self._request("/api/tags")
        models = response.get("models", [])
        return [str(model.get("name", "")) for model in models if model.get("name")]

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        return self.chat_messages(
            model,
            [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=temperature,
        )

    def chat_messages(self, model: str, messages: list[dict[str, str]], *, temperature: float = 0.2) -> str:
        if not model.strip():
            raise ValueError("Model name cannot be empty")
        if not messages or any(
            message.get("role") not in {"system", "user", "assistant"}
            or not isinstance(message.get("content"), str)
            for message in messages
        ):
            raise ValueError("Messages must contain valid chat roles and string content")
        response = self._request(
            "/api/chat",
            {
                "model": model,
                "stream": False,
                "messages": messages,
                **({"think": self.think} if self.think is not None else {}),
                "options": {
                    "temperature": temperature,
                    **({"num_predict": self.max_output_tokens}
                       if self.max_output_tokens is not None else {}),
                },
            },
        )
        message = response.get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        if not isinstance(content, str) or not content.strip():
            raise OllamaError("Ollama returned an empty message")
        return content.strip()
