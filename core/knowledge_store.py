"""Source-backed knowledge records for the personal research system."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class KnowledgeStore:
    """Store sources and source-linked claims in SQLite.

    This records provenance; it does not automatically prove that a source is
    authoritative or that a claim follows from it.
    """

    def __init__(self, db_path: str | Path = "data/research_system.sqlite3") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    publisher TEXT NOT NULL DEFAULT '',
                    published_at TEXT NOT NULL DEFAULT '',
                    accessed_at TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS claims (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('unreviewed','supported','contested','rejected')),
                    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS claim_sources (
                    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                    source_id INTEGER NOT NULL REFERENCES sources(id),
                    relationship TEXT NOT NULL DEFAULT 'supports',
                    PRIMARY KEY (claim_id, source_id, relationship)
                );
                CREATE INDEX IF NOT EXISTS idx_claim_status ON claims(status);
                CREATE TABLE IF NOT EXISTS source_revisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
                    content_sha256 TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE(source_id, content_sha256)
                );
                CREATE TABLE IF NOT EXISTS review_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    claim_id INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
                    source_id INTEGER NOT NULL REFERENCES sources(id),
                    source_sha256 TEXT NOT NULL DEFAULT '',
                    reviewer_label TEXT NOT NULL,
                    assessment TEXT NOT NULL CHECK(assessment IN ('supports','disputed','needs_more_evidence')),
                    rationale TEXT NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_review_notes_claim ON review_notes(claim_id,id);
                CREATE INDEX IF NOT EXISTS idx_source_sha ON sources(content_sha256);
            """)
            # Preserve each existing source's latest known fingerprint on migration.
            # Older fingerprints overwritten before migration cannot be reconstructed.
            conn.execute(
                """INSERT OR IGNORE INTO source_revisions(source_id,content_sha256,recorded_at)
                   SELECT id,content_sha256,accessed_at FROM sources
                   WHERE content_sha256 != ''"""
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _validate_url(url: str) -> str:
        url = url.strip()
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Source URL must be an absolute HTTP(S) URL")
        return url

    def add_source(
        self, url: str, title: str, *, publisher: str = "",
        published_at: str = "", content: str = "", notes: str = "",
    ) -> dict[str, Any]:
        url = self._validate_url(url)
        title = title.strip()
        if not title:
            raise ValueError("Source title cannot be empty")
        digest = sha256_text(content) if content else ""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO sources(url,title,publisher,published_at,accessed_at,content_sha256,notes)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(url) DO UPDATE SET
                     title=excluded.title,
                     publisher=CASE WHEN excluded.publisher != '' THEN excluded.publisher ELSE sources.publisher END,
                     published_at=CASE WHEN excluded.published_at != '' THEN excluded.published_at ELSE sources.published_at END,
                     accessed_at=excluded.accessed_at,
                     content_sha256=CASE WHEN excluded.content_sha256 != '' THEN excluded.content_sha256 ELSE sources.content_sha256 END,
                     notes=CASE WHEN excluded.notes != '' THEN excluded.notes ELSE sources.notes END""",
                (url, title, publisher.strip(), published_at.strip(), _now(), digest, notes.strip()),
            )
            row = conn.execute("SELECT * FROM sources WHERE url=?", (url,)).fetchone()
            if digest:
                conn.execute(
                    """INSERT OR IGNORE INTO source_revisions
                       (source_id,content_sha256,recorded_at) VALUES(?,?,?)""",
                    (row["id"], digest, _now()),
                )
        return dict(row)

    def add_claim(
        self, claim: str, source_ids: list[int], *, status: str = "unreviewed",
        confidence: float = 0.5, relationships: dict[int, str] | None = None,
    ) -> dict[str, Any]:
        claim = claim.strip()
        if not claim:
            raise ValueError("Claim cannot be empty")
        if status not in {"unreviewed", "supported", "contested", "rejected"}:
            raise ValueError(f"Invalid claim status: {status}")
        # Fail closed until an independently authenticated, auditable review
        # workflow exists. Source URLs/hashes are provenance, not proof.
        if status == "supported":
            raise ValueError("Supported status requires an independent review workflow; not available yet")
        if not 0 <= confidence <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        if not source_ids:
            raise ValueError("At least one source is required for a stored claim")
        relationships = relationships or {}
        with self._connect() as conn:
            placeholders = ",".join("?" for _ in set(source_ids))
            existing = conn.execute(
                f"SELECT id FROM sources WHERE id IN ({placeholders})", tuple(set(source_ids))
            ).fetchall()
            if len(existing) != len(set(source_ids)):
                raise ValueError("One or more source IDs do not exist")
            cur = conn.execute(
                "INSERT INTO claims(claim,status,confidence,created_at) VALUES(?,?,?,?)",
                (claim, status, float(confidence), _now()),
            )
            claim_id = int(cur.lastrowid)
            for source_id in sorted(set(source_ids)):
                relationship = relationships.get(source_id, "supports")
                if relationship not in {"supports", "contradicts", "context"}:
                    raise ValueError(f"Invalid source relationship: {relationship}")
                conn.execute(
                    "INSERT INTO claim_sources(claim_id,source_id,relationship) VALUES(?,?,?)",
                    (claim_id, source_id, relationship),
                )
            row = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
        return self._claim_dict(dict(row))

    @staticmethod
    def _claim_dict(row: dict[str, Any]) -> dict[str, Any]:
        return row

    def get_claim(self, claim_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM claims WHERE id=?", (claim_id,)).fetchone()
            if row is None:
                raise KeyError(f"Unknown claim: {claim_id}")
            links = conn.execute(
                """SELECT s.id, s.url, s.title, s.publisher, s.content_sha256, cs.relationship
                   FROM claim_sources cs JOIN sources s ON s.id=cs.source_id
                   WHERE cs.claim_id=? ORDER BY s.id""",
                (claim_id,),
            ).fetchall()
        result = dict(row)
        result["sources"] = [dict(item) for item in links]
        return result

    def add_review_note(
        self, claim_id: int, source_id: int, *, reviewer_label: str,
        assessment: str, rationale: str,
    ) -> dict[str, Any]:
        """Record a claimed review observation, never grant approval rights.

        reviewer_label is caller-provided and NOT an authenticated reviewer ID.
        Notes are append-only through this API, but SQLite is not tamper-proof.
        """
        reviewer_label = reviewer_label.strip()
        rationale = rationale.strip()
        if not reviewer_label or not rationale:
            raise ValueError("Review notes require a reviewer label and rationale")
        if assessment not in {"supports", "disputed", "needs_more_evidence"}:
            raise ValueError("Invalid review assessment")
        with self._connect() as conn:
            link = conn.execute(
                """SELECT s.content_sha256 FROM claim_sources cs
                   JOIN sources s ON s.id=cs.source_id
                   WHERE cs.claim_id=? AND cs.source_id=?""",
                (claim_id, source_id),
            ).fetchone()
            if link is None:
                raise ValueError("Review source must be linked to the claim")
            cur = conn.execute(
                """INSERT INTO review_notes
                   (claim_id,source_id,source_sha256,reviewer_label,assessment,rationale,recorded_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (claim_id, source_id, link["content_sha256"], reviewer_label,
                 assessment, rationale, _now()),
            )
            row = conn.execute("SELECT * FROM review_notes WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)

    def list_review_notes(self, claim_id: int) -> list[dict[str, Any]]:
        """List recorded review notes; no note implies claim verification."""
        with self._connect() as conn:
            if conn.execute("SELECT id FROM claims WHERE id=?", (claim_id,)).fetchone() is None:
                raise KeyError(f"Unknown claim: {claim_id}")
            rows = conn.execute(
                "SELECT * FROM review_notes WHERE claim_id=? ORDER BY id",
                (claim_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def audit_claim_evidence(self, claim_id: int) -> dict[str, Any]:
        """Report unresolved evidence risks without changing claim statuses.

        This is a local data consistency check, not independent source
        authentication, reviewer authorization, or scientific verification.
        """
        with self._connect() as conn:
            claim = conn.execute(
                "SELECT id,status FROM claims WHERE id=?", (claim_id,)
            ).fetchone()
            if claim is None:
                raise KeyError(f"Unknown claim: {claim_id}")
            links = conn.execute(
                """SELECT s.id,s.content_sha256,cs.relationship FROM claim_sources cs
                   JOIN sources s ON s.id=cs.source_id
                   WHERE cs.claim_id=? ORDER BY s.id""",
                (claim_id,),
            ).fetchall()
            notes = conn.execute(
                "SELECT source_id,source_sha256 FROM review_notes WHERE claim_id=? ORDER BY id",
                (claim_id,),
            ).fetchall()
        source_hashes = {x["id"]: x["content_sha256"] for x in links}
        flags = set()
        if claim["status"] == "supported":
            flags.add("legacy_supported_unverified")
        if not links or any(not item["content_sha256"] for item in links):
            flags.add("source_without_content_hash")
        if any(item["relationship"] == "contradicts" for item in links):
            flags.add("contradictory_source_link")
        if not notes:
            flags.add("no_review_notes")
        else:
            # A caller-supplied reviewer label is never verified identity.
            flags.add("reviewer_identity_unverified")
            if any(
                note["source_sha256"] != source_hashes.get(note["source_id"])
                for note in notes
            ):
                flags.add("review_source_digest_outdated")
        return {
            "claim_id": claim_id,
            "status": claim["status"],
            "flags": sorted(flags),
            "source_count": len(links),
            "review_note_count": len(notes),
            "independently_verified": False,
        }

    def audit_all_claims(
        self, *, status: str | None = None, limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Summarize a bounded page of evidence risks, never certify claims.

        flag_counts only counts the returned page, not the entire database.
        """
        allowed = {"unreviewed", "supported", "contested", "rejected"}
        if status is not None and status not in allowed:
            raise ValueError("Invalid claim status filter")
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("Audit limit must be an integer from 1 to 500")
        if type(offset) is not int or offset < 0:
            raise ValueError("Audit offset must be a nonnegative integer")
        where = "WHERE status=?" if status is not None else ""
        params = (status,) if status is not None else ()
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM claims {where}", params
            ).fetchone()[0]
            ids = conn.execute(
                f"SELECT id FROM claims {where} ORDER BY id LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
        records = [self.audit_claim_evidence(row["id"]) for row in ids]
        counts: dict[str, int] = {}
        for record in records:
            for flag in record["flags"]:
                counts[flag] = counts.get(flag, 0) + 1
        return {
            "total": total,
            "page_count": len(records),
            "limit": limit,
            "offset": offset,
            "status_filter": status,
            "flag_counts": counts,
            "records": records,
            "independently_verified": False,
        }

    def list_revisions(self, source_id: int) -> list[dict[str, Any]]:
        """List recorded content fingerprints; these are not full snapshots."""
        with self._connect() as conn:
            source = conn.execute("SELECT id FROM sources WHERE id=?", (source_id,)).fetchone()
            if source is None:
                raise KeyError(f"Unknown source: {source_id}")
            rows = conn.execute(
                """SELECT id,source_id,content_sha256,recorded_at
                   FROM source_revisions WHERE source_id=? ORDER BY id""",
                (source_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_sources(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
        return [dict(row) for row in rows]

    def list_claims(self, status: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if status is None:
                rows = conn.execute("SELECT * FROM claims ORDER BY id").fetchall()
            else:
                rows = conn.execute("SELECT * FROM claims WHERE status=? ORDER BY id", (status,)).fetchall()
        return [dict(row) for row in rows]
