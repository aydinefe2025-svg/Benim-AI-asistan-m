"""Determine which AI model providers have configured credentials.

Never log or return the credential values themselves.
"""


def available_providers(secrets):
    labels = []
    for name, label in (
        ("GROQ_API_KEY", "Groq GPT-OSS (Hızlı / Kesintisiz)"),
        ("GOOGLE_API_KEY", "Google Gemini (Gelişmiş Mod)"),
    ):
        try:
            token = secrets[name]
        except (KeyError, FileNotFoundError):
            continue
        if isinstance(token, str) and token.strip():
            labels.append(label)
    return tuple(labels)


def configured_credentials(secrets, environ):
    """Read credentials from Streamlit secrets or host environment, without logging values."""
    credentials = {}
    for name in ("GROQ_API_KEY", "GOOGLE_API_KEY"):
        try:
            value = secrets[name]
        except (KeyError, FileNotFoundError):
            value = None
        if not isinstance(value, str) or not value.strip():
            value = environ.get(name)
        if isinstance(value, str) and value.strip():
            credentials[name] = value.strip()
    return credentials
