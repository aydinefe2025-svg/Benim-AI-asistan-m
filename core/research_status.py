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


def label_unverified_claim_headings(output: str) -> str:
    """Downgrade model-authored verification headings for display only.

    The saved mission output is deliberately left untouched; this function is
    called only at the rendering boundary and does not verify any claim.
    """
    if not isinstance(output, str):
        raise ValueError("Mission output must be text")
    import re

    verified_titles = (
        "doğrulanmış gerçekler",
        "doğrulanmış olgular",
        "verified facts",
        "confirmed facts",
    )
    title_pattern = "|".join(re.escape(title) for title in verified_titles)
    heading = re.compile(
        rf"(?im)^(?P<prefix>\\s*(?:\#{{1,6}}\\s+|[-*]\\s+)?(?:\\*\\*)?)"
        rf"(?P<title>{title_pattern})(?P<suffix>(?:\\*\\*)?\\s*:?)\\s*$"
    )
    return heading.sub(
        lambda match: match.group("prefix")
        + "İncelenmemiş model iddiaları"
        + match.group("suffix"),
        output,
    )
