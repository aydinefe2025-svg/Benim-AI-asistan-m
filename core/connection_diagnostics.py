"""Read-only provider checks. Never return tokens, URLs or exception text."""
from __future__ import annotations


def check_provider(provider: str, credential: str | None, *, model: str = "",
                   request_get=None) -> dict:
    """List models or query Telegram getMe; never generate text or send messages."""
    if provider not in {"groq", "google", "telegram"}:
        raise ValueError("Unsupported provider")
    if not isinstance(credential, str) or not credential.strip():
        return {"status": "not_configured", "reachable": False, "authenticated": False}
    token = credential.strip()
    urls = {
        "groq": "https://api.groq.com/openai/v1/models",
        "google": "https://generativelanguage.googleapis.com/v1beta/models",
        "telegram": "https://api.telegram.org/bot" + token + "/getMe",
    }
    headers = {"Authorization": "Bearer " + token} if provider == "groq" else (
        {"x-goog-api-key": token} if provider == "google" else {})
    try:
        if request_get is None:
            import requests
            request_get = requests.get
        response = request_get(urls[provider], headers=headers, timeout=10,
                               allow_redirects=False)
        if response.status_code != 200:
            return {"status": "failed", "reachable": True,
                    "authenticated": False, "http_status": response.status_code}
        body = response.json()
        if provider == "telegram":
            valid = (body.get("ok") is True and
                     body.get("result", {}).get("is_bot") is True)
            return {"status": "verified" if valid else "failed",
                    "reachable": True, "authenticated": valid}
        collection = body["data" if provider == "groq" else "models"]
        if not isinstance(collection, list):
            raise ValueError("Invalid model list")
        field = "id" if provider == "groq" else "name"
        ids = {item[field].removeprefix("models/") for item in collection}
        result = {"status": "verified", "reachable": True, "authenticated": True}
        if model:
            result["model_available"] = model.removeprefix("models/") in ids
            # A paginated Google response cannot prove that an absent model
            # does not exist. Keep the distinction explicit.
            if not result["model_available"]:
                result["status"] = "unverified" if body.get("nextPageToken") else "model_missing"
        return result
    except Exception:
        return {"status": "unreachable_or_invalid", "reachable": False,
                "authenticated": False}
