"""Bounded client for the local, explicitly selected LoRA inference server."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.safety_policy import safe_response_for_prompt

TRAINED_LORA_URL = "http://127.0.0.1:8765"
TRAINED_LORA_LABEL = "LoRA (Yerel · Qwen3-8B deneysel)"
MAX_PROMPT_CHARS = 12_000
MAX_SYSTEM_CHARS = 4_000
MAX_INPUT_CHARS = 100_000
MAX_RESPONSE_BYTES = 256_000


class TrainedLoraError(RuntimeError):
    """The local LoRA endpoint is unavailable or returned an invalid result."""


def trained_lora_metadata(*, transport=None) -> dict[str, str] | None:
    """Return metadata only for the expected local Qwen3-8B adapter service."""
    sender = transport or urlopen
    try:
        with sender(Request(TRAINED_LORA_URL + "/health"), timeout=1) as response:
            data = json.loads(response.read(4096).decode("utf-8"))
        model = data.get("model")
        adapter = data.get("adapter")
        if (data.get("status") != "ok" or data.get("provider") != "trained_local"
                or model != "Qwen/Qwen3-8B" or not isinstance(adapter, str)
                or not re.fullmatch(r"candidate-[A-Za-z0-9_-]{1,80}", adapter)):
            return None
        return {"model": model, "adapter": adapter}
    except (HTTPError, URLError, OSError, ValueError, TypeError, AttributeError):
        return None


class TrainedLoraClient:
    """Chat adapter. It never grants the model direct filesystem/tool access."""

    def __init__(self, *, transport=None, timeout: int = 240,
                 max_output_tokens: int = 256) -> None:
        if type(max_output_tokens) is not int or not 32 <= max_output_tokens <= 512:
            raise ValueError("Local LoRA output budget must be between 32 and 512 tokens")
        self.transport = transport or urlopen
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        metadata = trained_lora_metadata(transport=self.transport)
        if metadata is None:
            raise TrainedLoraError("The expected local LoRA service is unavailable")
        self.last_model_used = f"{metadata['model']} + {metadata['adapter']}"
        self.metadata = metadata

    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str:
        del model, temperature  # The adapter server pins both model and decoding policy.
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > MAX_INPUT_CHARS:
            raise ValueError("Prompt is empty or exceeds the local LoRA limit")
        safe = safe_response_for_prompt(prompt)
        if safe is not None:
            return safe
        system_text = system.strip()[:MAX_SYSTEM_CHARS]
        user_text = prompt.strip()
        prefix = f"{system_text}\n\nKULLANICI İSTEĞİ:\n"
        available = MAX_PROMPT_CHARS - len(prefix)
        if available < 1:
            raise ValueError("System prompt exceeds the local LoRA limit")
        if len(user_text) > available:
            user_text = user_text[-available:]
        full_prompt = prefix + user_text
        request = Request(
            TRAINED_LORA_URL + "/generate",
            data=json.dumps({
                "prompt": full_prompt,
                "system": system_text,
                "user_prompt": user_text,
                "max_new_tokens": self.max_output_tokens,
            }, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.transport(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise TrainedLoraError("Local LoRA response exceeds the size limit")
            data = json.loads(raw.decode("utf-8"))
        except TrainedLoraError:
            raise
        except (HTTPError, URLError, OSError, ValueError, TypeError) as exc:
            raise TrainedLoraError("Local LoRA request failed") from exc
        if not isinstance(data, dict) or data.get("provider") != "trained_local":
            raise TrainedLoraError("Local LoRA returned an invalid response")
        answer = data.get("response")
        if not isinstance(answer, str) or not answer.strip():
            raise TrainedLoraError("Local LoRA returned an invalid response")
        return answer.strip()

