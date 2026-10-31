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
