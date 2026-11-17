"""Turn an authenticated owner's natural software request into a bounded code job.

The assistant's previous answer is untrusted context, never an authorization
signal. Nothing is queued unless the user explicitly requests implementation.
"""
from __future__ import annotations

import re
import unicodedata


_SECRET = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{16,}|"
    r"postgres(?:ql)?://|-----BEGIN [A-Z ]+PRIVATE KEY)",
    flags=re.IGNORECASE,
)


def _ascii(text):
    value = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in value if not unicodedata.combining(ch)).replace("ı", "i")


def actionable_solution(answer):
    """Only show the implementation action for an apparently concrete code fix."""
    if not isinstance(answer, str) or not answer.strip():
        return False
    if "kalıcı kuyruğa alındı" in answer.casefold():
        return False
    if _SECRET.search(answer):
        return False
    normalized = _ascii(answer)
    software = (
        "kod", "yazilim", "github", "render", "streamlit", "neon",
        "postgresql", "uygulama", "sohbet arayuzu", "test", "gorev kuyrugu",
    )
    verbs = (
        "duzelt", "ekle", "bagla", "test", "kur", "gelistir",
        "yayimla", "yayinla", "uygula", "guncelle", "onar",
    )
    return (any(word in normalized for word in software)
            and any(word in normalized for word in verbs))


def infer_code_goal(message, history):
    """A natural CANO action request; preserve old explicit routing unchanged."""
    if not isinstance(message, str):
        return None
    message = message.strip()
    if not 8 <= len(message) <= 1200 or _SECRET.search(message):
        return None
    normalized = " ".join(_ascii(message).split())
    if re.match(r"^(?:cano\s+)?(?:kod|gorev|gelistir|yazilim)\s*:", normalized):
        return None  # Existing explicit code or specialist task router owns this.
    if "?" in message or re.search(r"\b(misin|musun|miyiz|miyim)\b", normalized):
        return None
    # An explicit self-development command is a request for one bounded
    # developer job, not an invitation to generate another model-only plan.
    # Keep the goal stable so the persistent queue can deduplicate retries.
    if normalized.rstrip("!.") in {
        "kendini gelistir", "kendini gelistir cano",
        "cano kendini gelistir",
        "cano kendini gelistirmeye devam et",
    }:
        return (
            "CANO web uygulamasında doğrulanabilir bir yazılım iyileştirmesi yap: "
            "mevcut kod, test ve son gerçek hata kanıtını incele; tek bir küçük "
            "kullanıcı sorunu için başarısız RED testi oluştur, en dar kod "
            "düzeltmesini uygula, GREEN ve regresyon testlerini çalıştır. "
            "GitHub PR/CI makbuzu oluştur; güvenlik kapıları geçmeden "
            "birleştirme veya Render yayını yapma. Aynı görevi kopyalama; "
            "sırları, kullanıcı verisini, onaylı dersleri ve model "
            "ağırlıklarını izinsiz değiştirme. Ölçülebilir fark yoksa "
            "başarı iddiası yerine gerekçeli engel kaydet."
        )
    direct = (
        normalized.startswith("cano ")
        and any(word in normalized for word in (
            "kod", "yazilim", "web", "uygulama", "sohbet", "github",
            "render", "test", "yurutucu", "sistem",
        ))
        and bool(re.search(
            r"\b(duzelt|gelistir|uygula|kur|onar|yaz|ekle|bagla|test et|guncelle)\b",
            normalized,
        ))
    )
    if direct:
        return message

    followup = re.fullmatch(
        r"(?:cano\s+)?(?:bunu|bu cozumu|onerdigin cozumu|onerini)\s+"
        r"(?:yap|uygula|gerceklestir|koda dok|kodla)"
        r"|(?:tamam|peki)\s+(?:yap|uygula|kodla)"
        r"|(?:cano\s+)?(?:sen\s+)?(?:yap|uygula)\s+(?:artik|o zaman|ozaman)",
        normalized.rstrip(".!"),
    )
    if not followup or not isinstance(history, (list, tuple)):
        return None
    previous = next(
        (item.get("content", "") for item in reversed(history)
         if isinstance(item, dict) and item.get("role") == "assistant"
         and isinstance(item.get("content"), str)),
        "",
    )
    if not actionable_solution(previous):
        return None
    # Bounded, owner-approved context; never copy a secret into the queue.
    goal = ("CANO'nun önerdiği yazılım düzeltmesini gerçekten kodla, test et ve "
            "güvenliyse yayınla: " + previous.strip()[:1000])
    if len(goal) > 1200 or _SECRET.search(goal):
        return None
    return goal
