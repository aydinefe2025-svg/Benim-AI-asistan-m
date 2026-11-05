"""Explicit provider selection with safe offline fallback; no implicit network calls."""
import json
import os
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 1_000_000

def _trusted_groq_endpoint(url):
    try:
        parsed_url = urlsplit(url)
        port = parsed_url.port
    except (TypeError, ValueError):
        return False
    return (parsed_url.scheme == "https" and parsed_url.hostname == "api.groq.com"
            and parsed_url.path == "/openai/v1/chat/completions"
            and not parsed_url.username and not parsed_url.password
            and port in (None, 443) and not parsed_url.query and not parsed_url.fragment)

class ProviderError(RuntimeError):
    pass

def generate(prompt, provider="offline", *, transport=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt required")
    if provider == "offline":
        return {"provider": "offline", "status": "unavailable", "text": "", "reason": "No model called"}
    config = {
        "ollama": ("OLLAMA_URL", "http://localhost:11434/api/generate", "OLLAMA_MODEL", "qwen3:8b"),
        "groq": ("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions", "GROQ_MODEL", "openai/gpt-oss-120b"),
    }
    if provider not in config:
        raise ValueError("Unsupported provider")
    env_url, default_url, env_model, default_model = config[provider]
    url = os.getenv(env_url, default_url)
    model = os.getenv(env_model, default_model)
    if provider == "groq":
        if not _trusted_groq_endpoint(url):
            raise ProviderError("Groq endpoint must be the trusted HTTPS API endpoint")
        key = os.getenv("GROQ_API_KEY")
        if not key:
            raise ProviderError("GROQ_API_KEY is missing")
        payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 512}
        headers = {"Authorization": "Bearer " + key}
    else:
        # Qwen3 may spend its entire response budget in a hidden reasoning
        # trace unless thinking is explicitly disabled for this user-facing
        # text endpoint. Local models can also need longer than the cloud
        # request timeout while loading, especially on CPU-only machines.
        payload = {"model": model, "prompt": prompt, "stream": False, "think": False}
        headers = {}
    headers["Content-Type"] = "application/json"
    request = Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    sender = transport or urlopen
    try:
        with sender(request, timeout=120 if provider == "ollama" else 12) as response:
            raw_body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw_body) > MAX_RESPONSE_BYTES:
                raise ProviderError("Provider response exceeds size limit")
            body = json.loads(raw_body.decode("utf-8"))
        answer = body.get("response") if provider == "ollama" else body["choices"][0]["message"]["content"]
        if not isinstance(answer, str) or not answer.strip():
            raise ProviderError("Provider returned an empty response")
        return {"provider": provider, "status": "ok", "text": answer.strip()}
    except (HTTPError, URLError, OSError, ValueError, KeyError, IndexError, TypeError) as exc:
        raise ProviderError("Provider request failed: " + type(exc).__name__) from exc


