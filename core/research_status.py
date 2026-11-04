"""Presentation-level evidence labels for generated research drafts."""
from __future__ import annotations


UNVERIFIED_RESEARCH_LABEL = (
    "**Araştırma taslağı — bağımsız doğrulama yapılmadı.** "
    "Aşağıdaki metin model çıktısıdır; kaynak bağlantıları yalnızca adaydır. "
    "İddialar birincil kaynaklarla incelenmeden doğrulanmış kabul edilmemelidir."
)


def label_research_answer(answer: str, *, research_requested: bool) -> str:
    """Make research status explicit outside model-controlled output."""
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError("Research answer must be non-empty text")
    clean = answer.strip()
    if not research_requested:
        return clean
    return UNVERIFIED_RESEARCH_LABEL + "\n\n" + clean
