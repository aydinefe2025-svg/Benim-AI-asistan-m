"""Portable, explicit user-controlled memory for assistant context.

The library is exported/imported as JSON by the user. It is not model training,
and this module never writes memory to a server-side database.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1
MAX_ITEMS = 200
MAX_TEXT_CHARS = 2_000
MAX_TAGS = 12
MAX_TAG_CHARS = 40
MAX_IMPORT_BYTES = 512_000
TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
STOP_WORDS = {
    "ve", "veya", "ile", "bir", "bu", "şu", "o", "için", "gibi", "olan",
    "olarak", "daha", "çok", "en", "da", "de", "mi", "mı", "mu", "mü",
    "ben", "sen", "biz", "siz", "the", "and", "for", "with", "that", "this",
}


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("Memory text must be text")
    value = value.strip()
    if not value or len(value) > MAX_TEXT_CHARS:
        raise ValueError("Memory text length is invalid")
    return value


def new_memory(text: str, tags: list[str] | None = None) -> dict[str, str]:
    clean = _clean_text(text)
    clean_tags: list[str] = []
    for tag in tags or []:
        if not isinstance(tag, str):
            raise ValueError("Memory tags must be text")
        tag = tag.strip()[:MAX_TAG_CHARS]
        if tag and tag not in clean_tags:
            clean_tags.append(tag)
        if len(clean_tags) >= MAX_TAGS:
            break
    return {
        "id": str(uuid4()),
        "text": clean,
        "tags": clean_tags,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def normalize_library(payload: Any) -> list[dict[str, Any]]:
    """Validate an import payload and return safe normalized records."""
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported memory library format")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > MAX_ITEMS:
        raise ValueError("Memory library item count is invalid")
    normalized = []
    seen_ids: set[str] = set()
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError("Invalid memory item")
        text = _clean_text(raw.get("text"))
        item_id = raw.get("id")
        if not isinstance(item_id, str) or not item_id.strip() or len(item_id) > 100:
            item_id = str(uuid4())
        item_id = item_id.strip()
        if item_id in seen_ids:
            item_id = str(uuid4())
        seen_ids.add(item_id)
        tags = raw.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        clean_tags = []
        for tag in tags[:MAX_TAGS]:
            if isinstance(tag, str) and tag.strip():
                clean_tags.append(tag.strip()[:MAX_TAG_CHARS])
        created_at = raw.get("created_at")
        if not isinstance(created_at, str) or len(created_at) > 50:
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        normalized.append({
            "id": item_id, "text": text,
            "tags": clean_tags, "created_at": created_at,
        })
    return normalized


def export_library(items: list[dict[str, Any]]) -> str:
    normalized = normalize_library({"schema_version": SCHEMA_VERSION, "items": items})
    return json.dumps(
        {"schema_version": SCHEMA_VERSION, "items": normalized},
        ensure_ascii=False, indent=2,
    )


def import_library(raw: bytes | str) -> list[dict[str, Any]]:
    if isinstance(raw, bytes):
        if len(raw) > MAX_IMPORT_BYTES:
            raise ValueError("Memory library file is too large")
        raw = raw.decode("utf-8")
    elif len(raw.encode("utf-8")) > MAX_IMPORT_BYTES:
        raise ValueError("Memory library file is too large")
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid memory library JSON") from exc
    return normalize_library(payload)


def relevant_memories(items: list[dict[str, Any]], query: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return only lexical matches; never inject the entire library by default."""
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")
    query_tokens = {
        token.casefold() for token in TOKEN_RE.findall(query)
        if token.casefold() not in STOP_WORDS and len(token) > 1
    }
    if not query_tokens:
        return []
    ranked = []
    for item in items:
        text = str(item.get("text", ""))
        tags = item.get("tags", [])
        tokens = {token.casefold() for token in TOKEN_RE.findall(text + " " + " ".join(tags))}
        overlap = query_tokens & tokens
        if overlap:
            ranked.append((len(overlap) / len(query_tokens), len(overlap), item))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [row[2] for row in ranked[:limit] if row[0] >= 0.2]


def memory_context(items: list[dict[str, Any]], query: str, limit: int = 3) -> str:
    matches = relevant_memories(items, query, limit)
    if not matches:
        return ""
    lines = [
        "Kullanıcının açıkça kaydettiği, değiştirilebilir hafıza notları (model eğitimi değildir):"
    ]
    lines.extend(f"- {item['text']}" for item in matches)
    lines.append("Bunları yalnızca mevcut soruyla ilgiliyse kullan; güncel veya doğrulanmış gerçek sayma.")
    return "\n".join(lines)
