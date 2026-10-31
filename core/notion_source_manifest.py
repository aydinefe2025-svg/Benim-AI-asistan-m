"""Import explicitly exported Notion source metadata; no live Notion access.

This module does not fetch external URLs, authenticate sources or reviewers,
create scientific claims, or independently verify any research assertions.
All entries are validated before applying any changes; this is not a
cross-process database transaction guarantee.
"""
from __future__ import annotations

from typing import Any
from core.knowledge_store import KnowledgeStore


def import_source_manifest(
    store: KnowledgeStore,
    entries: list[dict[str, Any]],
) -> dict[str, int]:
    """Import a bounded source-only manifest idempotently.

    Required: absolute HTTP(S) URL, title, and explicit notion_page_id.
    Duplicate URLs within one manifest are only allowed for identical titles.
    Existing source metadata is preserved when optional values are omitted.
    """
    if not isinstance(entries, list):
        raise ValueError("Source manifest must be a list")
    if len(entries) > 500:
        raise ValueError("Source manifest exceeds 500 entries")
    normalized: dict[str, dict[str, str]] = {}
    duplicates = 0
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Each source must be an object")
        url = entry.get("url")
        title = entry.get("title")
        page_id = entry.get("notion_page_id")
        if not all(isinstance(x, str) and x.strip() for x in (url, title, page_id)):
            raise ValueError("Source URL, title, and notion_page_id are required")
        url = store._validate_url(url.strip())
        title = title.strip()
        page_id = page_id.strip()
        publisher = entry.get("publisher", "")
        if not isinstance(publisher, str):
            raise ValueError("Source publisher must be a string")
        candidate = {
            "url": url, "title": title, "notion_page_id": page_id,
            "publisher": publisher.strip(),
        }
        if url in normalized:
            if normalized[url]["title"] != title:
                raise ValueError("Conflicting titles for the same source URL")
            duplicates += 1
            continue
        normalized[url] = candidate

    existing = {x["url"]: x["id"] for x in store.list_sources()}
    inserted = 0
    for item in normalized.values():
        url = item["url"]
        # This is provenance metadata, not the content of the URL.
        source_note = "Notion page reference: " + item["notion_page_id"]
        store.add_source(
            url, item["title"], publisher=item["publisher"],
            notes=source_note,
        )
        if url not in existing:
            inserted += 1
    return {
        "imported": inserted,
        "duplicates_skipped": duplicates,
        "processed_unique": len(normalized),
        "claim_count_created": 0,
    }
