"""Explicit provider selection with safe offline fallback; no implicit network calls."""
import json
import os
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 1_000_000
TRAINED_LOCAL_URL = "http://127.0.0.1:8765"

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

def trained_local_ready(*, transport=None):
    """Return true only when the loopback adapter server answers healthy."""
    sender = transport or urlopen
    try:
        with sender(Request(TRAINED_LOCAL_URL + "/health", method="GET"), timeout=1) as response:
            body = json.loads(response.read(1024).decode("utf-8"))
        return body.get("status") == "ok" and body.get("provider") == "trained_local"
    except (HTTPError, URLError, OSError, ValueError, TypeError):
        return False

class ProviderError(RuntimeError):
    pass

GROQ_MODEL_OPTIONS = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    "meta-models/muse-spark-open",
)

def _safe_groq_error_code(exc):
    """Read a bounded machine code/type; never expose provider prose."""
    try:
        raw = exc.read(4096)
        if not raw.strip():
            return "empty_error_response"
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError, TypeError):
        return "non_json_error_response"
    pending = [payload]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            code = value.get("code")
            if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", code):
                return code
            error_type = value.get("type")
            if isinstance(error_type, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", error_type):
                return error_type
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
    return "json_error_without_machine_code"


def _safe_http_error_origin(exc):
    """Return only allowlisted response source/content classes, never raw headers."""
    headers = getattr(exc, "headers", None)
    def header(name):
        if not headers:
            return ""
        return (headers.get(name) or headers.get(name.title()) or "").lower()
    server = header("server")
    if "groq" in server:
        source = "groq"
    elif "cloudflare" in server:
        source = "cloudflare"
    elif "render" in server:
        source = "render"
    elif server:
        source = "other_server"
    else:
        source = "unknown_server"
    content_type = header("content-type")
    if "json" in content_type:
        body_type = "json"
    elif "html" in content_type:
        body_type = "html"
    elif content_type:
        body_type = "other"
    else:
        body_type = "unknown"
    return source + "/" + body_type


def diagnose_groq_access(api_key, model_id, *, transport=None):
    """Check key-scoped model listing without generating text or returning secrets."""
    if not isinstance(api_key, str) or not api_key.strip():
        return {"reachable": False, "model_available": False, "http_status": None,
                "error_code": None}
    request = Request(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": "Bearer " + api_key.strip(),
                 "User-Agent": "Benim-AI-asistan-m/1.0"},
        method="GET",
    )
    sender = transport or urlopen
    try:
        with sender(request, timeout=10) as response:
            raw = response.read(64_000)
        payload = json.loads(raw.decode("utf-8"))
        models = payload.get("data", []) if isinstance(payload, dict) else []
        model_ids = {item.get("id") for item in models if isinstance(item, dict)}
        return {"reachable": True, "model_available": model_id in model_ids,
                "http_status": 200, "error_code": None}
    except HTTPError as exc:
        return {"reachable": False, "model_available": False,
                "http_status": exc.code, "error_code": _safe_groq_error_code(exc),
                "response_origin": _safe_http_error_origin(exc)}
    except (URLError, OSError, UnicodeDecodeError, ValueError, TypeError):
        return {"reachable": False, "model_available": False,
                "http_status": None, "error_code": None}


def groq_test_key():
    """Return the separately configured test credential, if present."""
    return (os.getenv("GROQ_API_KEY_TEST") or "").strip()


def groq_active_key():
    """Select the test credential only after the explicit activation flag is set."""
    if os.getenv("GROQ_API_KEY_TEST_ACTIVE", "").strip() == "1":
        return groq_test_key()
    return (os.getenv("GROQ_API_KEY") or "").strip()

def generate(prompt, provider="offline", *, transport=None, model=None, system_prompt=None):
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Prompt required")
    if provider == "offline":
        return {"provider": "offline", "status": "unavailable", "text": "", "reason": "No model called"}
    if provider == "trained_local":
        request = Request(
            TRAINED_LOCAL_URL + "/generate",
            data=json.dumps({"prompt": prompt}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        sender = transport or urlopen
        try:
            with sender(request, timeout=240) as response:
                raw_body = response.read(MAX_RESPONSE_BYTES + 1)
                if len(raw_body) > MAX_RESPONSE_BYTES:
                    raise ProviderError("Provider response exceeds size limit")
                body = json.loads(raw_body.decode("utf-8"))
            answer = body.get("response")
            if body.get("provider") != "trained_local" or not isinstance(answer, str) or not answer.strip():
                raise ProviderError("Trained local model returned an invalid response")
            return {"provider": "trained_local", "status": "ok", "text": answer.strip()}
        except ProviderError:
            raise
        except (HTTPError, URLError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ProviderError("Trained local provider request failed: " + type(exc).__name__) from exc
    config = {
        "ollama": ("OLLAMA_URL", "http://localhost:11434/api/generate", "OLLAMA_MODEL", "qwen3:8b"),
        "groq": ("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions", "GROQ_MODEL", "openai/gpt-oss-120b"),
    }
    if provider not in config:
        raise ValueError("Unsupported provider")
    env_url, default_url, env_model, default_model = config[provider]
    url = os.getenv(env_url, default_url)
    model = model or os.getenv(env_model, default_model)
    if provider == "groq" and model not in GROQ_MODEL_OPTIONS:
        raise ValueError("Unsupported Groq model")
    if provider == "groq":
        if not _trusted_groq_endpoint(url):
            raise ProviderError("Groq endpoint must be the trusted HTTPS API endpoint")
        key = groq_active_key()
        if not key:
            raise ProviderError("Active Groq API key is missing")
        messages = ([{"role": "system", "content": system_prompt}]
                    if isinstance(system_prompt, str) and system_prompt.strip() else [])
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "max_tokens": 512}
        headers = {"Authorization": "Bearer " + key,
                   "User-Agent": "Benim-AI-asistan-m/1.0"}
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
    except HTTPError as exc:
        if provider == "groq":
            code = _safe_groq_error_code(exc)
            if code == "invalid_api_key" or exc.code == 401:
                message = "Groq API anahtarı geçersiz veya iptal edilmiş (HTTP " + str(exc.code) + ")."
            elif code in ("permission_denied", "permissions_error", "insufficient_permissions", "project_permission_denied",
                          "project_not_found", "invalid_project", "organization_disabled",
                          "organization_restricted"):
                message = "Groq anahtarının proje/organizasyon erişimi reddedildi (HTTP " + str(exc.code) + ")."
            elif code in ("model_not_found", "model_decommissioned", "model_not_available", "model_access_denied"):
                message = "Groq bu model için erişim vermedi; model seçimini/proje iznini kontrol edin (HTTP " + str(exc.code) + ")."
            elif exc.code == 403:
                message = "Groq erişimi reddetti; proje veya model iznini kontrol edin (HTTP 403)."
            elif exc.code in (400, 404):
                message = "Groq bu modeli veya isteği kabul etmedi; model seçimini kontrol edin (HTTP " + str(exc.code) + ")."
            elif exc.code == 429:
                message = "Groq kota veya istek hızı sınırına ulaşıldı (HTTP 429)."
            elif exc.code >= 500:
                message = "Groq geçici sunucu hatası verdi (HTTP " + str(exc.code) + ")."
            else:
                message = "Groq isteği reddedildi (HTTP " + str(exc.code) + ")."
            if code:
                message += " Groq hata kodu: " + code + "."
            raise ProviderError(message) from None
        raise ProviderError("Provider HTTP request failed (HTTP " + str(exc.code) + ").") from None
    except (URLError, OSError) as exc:
        label = "Groq" if provider == "groq" else "Provider"
        raise ProviderError(label + " network request failed (" + type(exc).__name__ + ").") from None
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        label = "Groq" if provider == "groq" else "Provider"
        raise ProviderError(label + " returned an invalid response (" + type(exc).__name__ + ").") from None


