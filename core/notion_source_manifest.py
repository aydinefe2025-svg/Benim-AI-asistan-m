"""Import explicitly exported Notion source metadata; no live Notion access.

This module does not fetch external URLs, authenticate sources or reviewers,
create scientific claims, or independently verify any research assertions.
All entries are validated before applying any changes. The write batch
uses a single SQLite transaction and rolls back on database errors.
"""
from __future__ import annotations

from typing import Any
from core.knowledge_store import KnowledgeStore, _now


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
    research_links: dict[str, tuple[str, str]] = {}
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
        research_id = entry.get("research_id")
        if research_id is not None:
            if not isinstance(research_id, str) or not research_id.strip():
                raise ValueError("research_id must be a non-empty string")
            research_id = research_id.strip()
            previous = research_links.get(research_id)
            if previous is not None and previous != (url, page_id):
                raise ValueError("Research ID cannot reference multiple URLs/pages")
            research_links[research_id] = (url, page_id)
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

    # A single transaction protects the *entire* batch from partial commits.
    # Do not call store.add_source here: it opens and commits its own
    # connection for each source, defeating the batch rollback contract.
    inserted = 0
    with store._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for item in normalized.values():
            url = item["url"]
            existed = conn.execute(
                "SELECT id FROM sources WHERE url=?", (url,)
            ).fetchone() is not None
            # The source note is metadata; it does not certify the article.
            source_note = "Notion page reference: " + item["notion_page_id"]
            conn.execute(
                """INSERT INTO sources
                   (url,title,publisher,published_at,accessed_at,content_sha256,notes)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET
                     title=excluded.title,
                     publisher=CASE WHEN excluded.publisher != ''
                         THEN excluded.publisher ELSE sources.publisher END,
                     accessed_at=excluded.accessed_at,
                     notes=CASE WHEN sources.notes = ''
                         THEN excluded.notes ELSE sources.notes END""",
                (url, item["title"], item["publisher"], "", _now(), "", source_note),
            )
            if not existed:
                inserted += 1
        # Verify identity assignments and write links inside the same
        # transaction as source changes so any conflict rolls everything back.
        for research_id, (url, page_id) in research_links.items():
            source = conn.execute(
                "SELECT id FROM sources WHERE url=?", (url,)
            ).fetchone()
            stored = conn.execute(
                """SELECT l.source_id,l.notion_page_id,s.url
                   FROM notion_source_links l JOIN sources s ON s.id=l.source_id
                   WHERE l.research_id=?""", (research_id,)
            ).fetchone()
            if stored is not None and stored["url"] != url:
                raise ValueError("Research ID already assigned to another source URL")
            if stored is not None and stored["notion_page_id"] != page_id:
                raise ValueError("Research ID already assigned to another Notion page")
            if stored is None:
                conn.execute(
                    """INSERT INTO notion_source_links
                       (research_id,source_id,notion_page_id) VALUES(?,?,?)""",
                    (research_id, source["id"], page_id),
                )
    return {
        "imported": inserted,
        "duplicates_skipped": duplicates,
        "processed_unique": len(normalized),
        "claim_count_created": 0,
    }
