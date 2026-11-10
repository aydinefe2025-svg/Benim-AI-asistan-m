"""Deterministic pre-inference safety checks for credential and billing requests."""
from __future__ import annotations

import re
import unicodedata


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold().replace("ı", "i"))
    return "".join(char for char in value if not unicodedata.combining(char))


def _latest_user_turn(prompt: str) -> str:
    """Avoid acting on quoted earlier assistant text in serialized conversations."""
    matches = list(re.finditer(r"(?m)^(user|assistant):\s*", prompt, re.IGNORECASE))
    if not matches:
        return prompt
    users = [index for index, match in enumerate(matches)
             if match.group(1).casefold() == "user"]
    if not users:
        return prompt
    index = users[-1]
    start = matches[index].end()
    end = matches[index + 1].start() if index + 1 < len(matches) else len(prompt)
    return prompt[start:end]


def safe_response_for_prompt(prompt: str) -> str | None:
    """Return a fixed answer for unsafe requests, before any model or tool call."""
    if not isinstance(prompt, str):
        return None
    text = _normalize(_latest_user_turn(prompt))
    credential = re.search(
        r"\b(api[\s_-]*key|api\s*anahtar\w*|access[\s_-]*key|token|"
        r"\w*secret\w*|credential|sifre\w*|parola\w*|anahtar\w*)\b", text,
    )
    disclosure = re.search(
        r"\b(yazdir\w*|print\w*|logla\w*|log\w*|gunluge\w*|terminal\w*|"
        r"cikti\w*|ekrana\w*|goster\w*|paylas\w*|ifsa\w*)\b", text,
    )
    if credential and disclosure:
        return (
            "Hayır. API anahtarını, tokenı veya parolayı terminale, loglara ya da "
            "ekrana yazdırma. Hata ayıklarken değeri tamamen maskele; gerçek bir "
            "gizli bilgi açığa çıktıysa ilgili anahtarı iptal edip yenile."
        )

    financial = re.search(r"\b(ucretli|paid|faturalandirma|odeme|para|kredi)\w*\b", text)
    unauthorized = re.search(
        r"\b(sormadan|izinsiz|onaysiz|izin\s+almadan|onay\s+almadan|"
        r"without\s+(?:asking|permission|approval)|without\s+consent)\b", text,
    )
    enable_or_spend = re.search(
        r"\b(ac|aktiflestir\w*|kullan\w*|baslat\w*|harca\w*|enable\w*|"
        r"activate\w*|use\w*|spend\w*|start\w*)\b", text,
    )
    if financial and unauthorized and enable_or_spend:
        return (
            "Ücretli bir hizmeti etkinleştirme, kullanma veya harcama yapma; "
            "önce kullanıcıdan açık onay alınmalı. Bu istekte hiçbir ücretli "
            "işlem başlatılmadı."
        )
    return None

