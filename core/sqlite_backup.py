"""Non-destructive, one-file SQLite snapshot backup and restore.

Exports create new files only; no in-place replacement or scheduled automation.
Uses SQLite's online backup API, not raw file copying, to support WAL databases.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


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
        return {"integrity_check": "ok", **counts}
    except BaseException:
        dest.unlink(missing_ok=True)
        raise


def backup_research_db(source: str | Path, destination: str | Path) -> dict[str, int | str]:
    """Make a new consistent SQLite snapshot; never overwrite the destination."""
    src = _source_checked(source)
    return _copy_database(src, destination)


def restore_research_db(backup: str | Path, destination: str | Path) -> dict[str, int | str]:
    """Restore a validated snapshot to a *new* path only; never replace live DB."""
    src = _source_checked(backup)
    return _copy_database(src, destination)
