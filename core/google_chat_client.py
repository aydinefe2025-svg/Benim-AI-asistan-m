"""Small, bounded Google Gen AI adapter for opted-in fallback calls."""
from __future__ import annotations

from core.safety_policy import safe_response_for_prompt

from core.provider_failure import copy_safe_failure_metadata


class GoogleChatClient:
    def __init__(self, api_key: str, *, timeout: float = 20.0) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Google API key is required")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Timeout must be positive")
        self._api_key = api_key.strip()
        self.timeout = float(timeout)

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        safe_response = safe_response_for_prompt(prompt)
        if safe_response is not None:
            return safe_response
        if not model.strip():
            raise ValueError("Model name cannot be empty")
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(
                api_key=self._api_key,
                http_options=types.HttpOptions(
                    timeout=int(self.timeout * 1000),
                    retry_options=types.HttpRetryOptions(attempts=1),
                ),
            )
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        max_output_tokens=1200,
                        temperature=temperature,
                    ),
                )
            finally:
                close = getattr(client, "close", None)
                if callable(close):
                    close()
            content = response.text
        except Exception as exc:
            failure = RuntimeError(f"Google request failed ({type(exc).__name__})")
            copy_safe_failure_metadata(exc, failure)
            raise failure from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Google returned no usable text")
        return content.strip()

