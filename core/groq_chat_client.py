"""Small, bounded Groq chat adapter for explicitly approved fallback runs."""
from __future__ import annotations


class GroqChatClient:
    def __init__(self, api_key: str, *, timeout: float = 25.0) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("Groq API key is required")
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ValueError("Timeout must be positive")
        self._api_key = api_key.strip()
        self.timeout = float(timeout)

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        if not model.strip():
            raise ValueError("Model name cannot be empty")
        try:
            from groq import Groq

            response = Groq(
                api_key=self._api_key, timeout=self.timeout, max_retries=0
            ).chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                temperature=temperature,
            )
            content = response.choices[0].message.content
        except Exception as exc:
            raise RuntimeError(f"Groq request failed ({type(exc).__name__})") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Groq returned no usable text")
        return content.strip()

