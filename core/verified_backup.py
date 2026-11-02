"""Consistent, integrity-checked SQLite backup for research records."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_sqlite_backup(source: str | Path, destination: str | Path) -> dict[str, str | int]:
    """Back up a live SQLite database without replacing an existing backup.

    The source must already exist. SQLite's backup API captures a consistent
    snapshot even when the source is in WAL mode.
    """
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == destination:
        raise ValueError("Source and destination must differ")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".sqlite-backup-", suffix=".tmp", dir=destination.parent,
            delete=False,
        ) as temp:
            temp_name = temp.name
        with sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True) as src:
            with sqlite3.connect(temp_name) as dst:
                src.backup(dst)
                result = dst.execute("PRAGMA integrity_check").fetchone()
                if result != ("ok",):
                    raise RuntimeError(f"Backup integrity check failed: {result}")
        # Exclusive creation prevents accidentally replacing an existing backup.
        with open(temp_name, "rb") as original:
            with destination.open("xb") as output:
                for chunk in iter(lambda: original.read(1024 * 1024), b""):
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
        return {
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "integrity": "ok",
        }
    except BaseException:
        # A failed copy must not leave a misleading partial backup.
        if destination.exists() and temp_name is not None:
            # Only remove files created by this invocation; existing destinations
            # are rejected before the temporary file is created.
            destination.unlink()
        raise
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)
