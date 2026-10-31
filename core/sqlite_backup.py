"""Non-destructive, one-file SQLite snapshot backup and restore.

Exports create new files only; no in-place replacement or scheduled automation.
Uses SQLite's online backup API, not raw file copying, to support WAL databases.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from pathlib import Path


def _sha256_file(path: Path) -> str:
    """Hash actual on-disk bytes; callers must retain the digest separately."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_checked(path: str | Path) -> Path:
    src = Path(path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"Database file does not exist: {src}")
    try:
        with sqlite3.connect(src.as_uri() if src.is_absolute() else src.resolve().as_uri(), uri=True) as conn:
            result = conn.execute("PRAGMA integrity_check").fetchone()
            if result is None or result[0] != "ok":
                raise ValueError("SQLite integrity check failed")
            # Avoid treating an arbitrary valid SQLite database as our research archive.
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            expected = {"sources", "claims", "source_revisions", "review_notes", "notion_source_links"}
            if not expected.issubset(tables):
                raise ValueError("Not a supported research database schema")
    except sqlite3.DatabaseError as exc:
        raise ValueError("Invalid SQLite backup") from exc
    return src


def _copy_database(source: Path, destination: str | Path) -> dict[str, int | str]:
    dest = Path(destination).expanduser()
    if source.resolve() == dest.resolve():
        raise FileExistsError("Cannot overwrite the source database")
    if dest.exists():
        raise FileExistsError(f"Destination already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Reserve the path exclusively. This is not cross-host/object-store atomicity.
    with dest.open("xb"):
        pass
    try:
        with sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True) as src:
            with sqlite3.connect(dest) as dst:
                src.backup(dst)
                check = dst.execute("PRAGMA integrity_check").fetchone()[0]
                if check != "ok":
                    raise ValueError("Backup destination failed integrity check")
                counts = {
                    "source_count": dst.execute("SELECT COUNT(*) FROM sources").fetchone()[0],
                    "claim_count": dst.execute("SELECT COUNT(*) FROM claims").fetchone()[0],
                }
        return {"integrity_check": "ok", "sha256": _sha256_file(dest), **counts}
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def backup_research_db(source: str | Path, destination: str | Path) -> dict[str, int | str]:
    """Make a new consistent SQLite snapshot; never overwrite the destination."""
    src = _source_checked(source)
    return _copy_database(src, destination)


def restore_research_db(
    backup: str | Path, destination: str | Path, *,
    expected_sha256: str | None = None,
) -> dict[str, int | str]:
    """Restore to a new path; optionally verify a separately recorded digest.

    SHA-256 detects changes only if the expectation comes from a trusted,
    independently retained record. It does not authenticate its creator.
    """
    src = _source_checked(backup)
    if expected_sha256 is not None:
        if not isinstance(expected_sha256, str) or re.fullmatch(
            r"[0-9a-fA-F]{64}", expected_sha256
        ) is None:
            raise ValueError("Expected SHA-256 must be 64 hex characters")
        actual = _sha256_file(src)
        if not hmac.compare_digest(actual, expected_sha256.lower()):
            raise ValueError("Backup SHA-256 does not match expected digest")
    return _copy_database(src, destination)


def backup_with_receipt(
    source: str | Path, destination: str | Path, receipt_path: str | Path,
) -> dict[str, int | str]:
    """Make a backup plus a distinct, new metadata receipt file.

    The receipt should be copied to a trusted location separately.
    """
    dest = Path(destination).expanduser()
    receipt = Path(receipt_path).expanduser()
    if dest.resolve() == receipt.resolve():
        raise ValueError("Backup and receipt paths must differ")
    if dest.exists() or receipt.exists():
        raise FileExistsError("Backup or receipt path already exists")
    # Create only the requested new backup path.
    result = backup_research_db(source, dest)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": 1,
        "sha256": result["sha256"],
        "source_count": result["source_count"],
        "claim_count": result["claim_count"],
    }
    with receipt.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, sort_keys=True, indent=2)
        stream.write("\n")
    return result


def recovery_drill(
    backup: str | Path, receipt_path: str | Path, destination: str | Path,
) -> dict[str, int | str | bool]:
    """Restore into a new path after validating a separate receipt."""
    try:
        receipt = json.loads(Path(receipt_path).read_text(encoding="utf-8"))
        if not isinstance(receipt, dict) or receipt.get("schema_version") != 1:
            raise ValueError("Invalid receipt schema")
        sha = receipt["sha256"]
        sources = receipt["source_count"]
        claims = receipt["claim_count"]
        if (type(sources) is not int or sources < 0 or
                type(claims) is not int or claims < 0):
            raise ValueError("Invalid receipt counts")
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError) as exc:
        raise ValueError("Invalid receipt") from exc
    # The original backup API refuses to overwrite any destination.
    result = restore_research_db(backup, destination, expected_sha256=sha)
    if (result["source_count"] != sources or
            result["claim_count"] != claims):
        raise ValueError("Recovered record counts differ from receipt")
    return {"verified": True, **result}
