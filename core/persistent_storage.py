"""Fail-closed production SQLite path validation.

A successful CI run on an ephemeral runner does not imply durable storage.
This guard prevents silently treating a relative or temporary SQLite file as
a production database. It does not provision a persistent volume.
"""
from __future__ import annotations

import os
from pathlib import Path


class PersistentStorageError(RuntimeError):
    """Production storage cannot be proven safe from its configuration."""


def validate_production_sqlite_path(
    path: str | os.PathLike[str] | None,
    *,
    persistent_root: str | os.PathLike[str] | None,
) -> Path:
    """Validate a DB path against an explicitly configured mounted volume root.

    This is a configuration guard, not proof of volume persistence: the
    deployment platform must separately confirm the mount and restart test.
    """
    if not path or not persistent_root:
        raise PersistentStorageError(
            "Production SQLite requires DATABASE_PATH and PERSISTENT_VOLUME_ROOT"
        )
    db = Path(path).expanduser()
    root = Path(persistent_root).expanduser()
    if not db.is_absolute() or not root.is_absolute():
        raise PersistentStorageError("Production storage paths must be absolute")
    db = db.resolve(strict=False)
    root = root.resolve(strict=False)
    if root == Path("/") or root == Path("/tmp") or root.is_relative_to(Path("/tmp")):
        raise PersistentStorageError("Persistent root cannot be filesystem root or /tmp")
    if db == root or not db.is_relative_to(root):
        raise PersistentStorageError("Database must be inside persistent volume root")
    if db.suffix not in {".sqlite", ".sqlite3", ".db"}:
        raise PersistentStorageError("Database must use an SQLite file extension")
    return db


def configured_production_db() -> Path:
    return validate_production_sqlite_path(
        os.environ.get("DATABASE_PATH"),
        persistent_root=os.environ.get("PERSISTENT_VOLUME_ROOT"),
    )
