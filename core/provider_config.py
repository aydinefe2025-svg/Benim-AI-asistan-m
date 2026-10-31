"""Determine which AI model providers have configured credentials.

Never log or return credential values through diagnostics.
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
    """Read credentials from Streamlit secrets or host environment."""
    credentials = {}
    for name in ("GROQ_API_KEY", "GOOGLE_API_KEY"):
        try:
            value = secrets[name]
        except Exception:
            # Streamlit raises StreamlitSecretNotFoundError when no secrets
            # file/configuration exists; still allow host environment fallback.
            value = None
        if not isinstance(value, str) or not value.strip():
            value = environ.get(name)
        if isinstance(value, str) and value.strip():
            credentials[name] = value.strip()
    return credentials


def credential_presence(credentials):
    """Return only booleans for safe diagnostics; never return key contents."""
    return {
        name: bool(isinstance(credentials.get(name), str) and credentials[name].strip())
        for name in ("GROQ_API_KEY", "GOOGLE_API_KEY")
    }
