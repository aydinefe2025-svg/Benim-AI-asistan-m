"""Explainable lexical comparison of a claim with user-provided source text.

This is a passage finder, not a semantic entailment or scientific truth model.
It never fetches URLs, changes claim status, or treats lexical similarity as proof.
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

MAX_CLAIM_CHARS = 2_000
MAX_SOURCE_CHARS = 200_000
MAX_SOURCES = 8
MAX_RESULTS = 5

_TOKEN = re.compile(r"[^\W_]+(?:['’][^\W_]+)?", re.UNICODE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_STOPWORDS = frozenset("""
    a an and are as at be been by can could did do does for from had has have he her
    hers him his how i if in into is it its may might of on or our she should that the
    their them there these they this those to was we were what when where which who
    will with would you your ve bir bazı bu da de daha diye en gibi için ile ise mı mi
    mu mü ne o olarak ve veya ya hem çok tüm şu üst altında üzerine olan olacak edildi
""".split())
_NEGATION = frozenset({
    "no", "not", "never", "without", "neither", "nor", "cannot", "can't", "doesn't",
    "isn't", "wasn't", "failed", "fails", "absent", "lack", "lacks", "didn't",
    "değil", "yok", "olmadı", "olmadığını", "bulunmadı", "saptanmadı", "gözlenmedi",
    "azaltmaz", "artırmaz", "arttırmaz", "önlemez", "engellemez", "sağlamaz",
})


def _tokens(text: str) -> list[str]:
    return [word.casefold().replace("’", "'") for word in _TOKEN.findall(text)
            if len(word) > 1 and
            (word.casefold().replace("’", "'") in _NEGATION or
             word.casefold() not in _STOPWORDS)]


def _valid_source(source: object) -> tuple[str, str, str]:
    if not isinstance(source, dict):
        raise ValueError("Each source must be an object")
    title = source.get("title")
    url = source.get("url")
    content = source.get("content")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("Source title is required")
    if not isinstance(url, str):
        raise ValueError("Source URL is required")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Source URL must be an absolute HTTP(S) URL")
    if not isinstance(content, str):
        raise ValueError("Source text must be a string")
    if len(content) > MAX_SOURCE_CHARS:
        raise ValueError("Source text exceeds the comparison limit")
    return title.strip()[:300], url, content


def compare_claim_to_sources(claim: str, sources: list[dict]) -> dict:
    """Return ranked, cited source passages and conservative text-match labels.

    `possible_support` only means the passage shares claim terms and contains no
    detected negation mismatch. It does not mean that the passage entails the
    claim. Contradiction detection is deliberately limited to explicit negation.
    """
    if not isinstance(claim, str) or not claim.strip():
        raise ValueError("Claim text is required")
    if len(claim) > MAX_CLAIM_CHARS:
        raise ValueError("Claim exceeds the comparison limit")
    if not isinstance(sources, list) or len(sources) > MAX_SOURCES:
        raise ValueError(f"Provide at most {MAX_SOURCES} source records")

    claim_words = _tokens(claim)
    claim_terms = set(claim_words)
    if not claim_terms:
        raise ValueError("Claim must contain at least one searchable term")
    claim_negated = bool(claim_terms & _NEGATION)
    results = []
    for source in sources:
        title, url, content = _valid_source(source)
        if not content.strip():
            continue
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for passage in _SENTENCE.split(content):
            passage = passage.strip()
            if not passage:
                continue
            passage_terms = set(_tokens(passage))
            matched = claim_terms & passage_terms
            overlap = len(matched) / len(claim_terms)
            # Require more than a generic single-word match where possible.
            minimum = 1 if len(claim_terms) == 1 else 2
            if len(matched) < minimum or overlap < 0.30:
                continue
            negation_mismatch = bool(passage_terms & _NEGATION) != claim_negated
            results.append({
                "assessment": "possible_contradiction" if negation_mismatch else "possible_support",
                "match_ratio": round(overlap, 3),
                "matched_terms": sorted(matched),
                "passage": passage[:1200],
                "citation": {"title": title, "url": url, "compared_text_sha256": digest},
                "limits": "Lexical overlap only; not entailment, source-authenticity, or scientific verification.",
            })
    results.sort(key=lambda item: (-item["match_ratio"], item["citation"]["url"], item["passage"]))
    results = results[:MAX_RESULTS]
    if not results:
        assessment = "insufficient_text_match"
    elif any(item["assessment"] == "possible_contradiction" for item in results):
        assessment = "possible_contradiction"
    else:
        assessment = "possible_support"
    return {
        "claim": claim.strip(),
        "assessment": assessment,
        "passages": results,
        "sources_examined": len(sources),
        "independently_verified": False,
        "claim_status_changed": False,
        "method": "bounded_unicode_token_overlap_and_explicit_negation",
    }

