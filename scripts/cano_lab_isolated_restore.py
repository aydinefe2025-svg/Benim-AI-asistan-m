"""Restore an authenticated v2 laboratory archive to a NEW isolated PostgreSQL DB.

Offline operator tool. No writes to the CANO live service, no schema migration,
no automatic deployment. The lab-only import is NOT a full PostgreSQL restore.
The destination must be a separate cano_restore_* database with the preexisting
schema, a privileged staging operator role, and an entirely empty lab table.
"""
from __future__ import annotations

import argparse
import base64
from getpass import getpass
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit, parse_qsl

from core.backup_encryption import decrypt_backup, MAX_PLAINTEXT_BYTES
from core.cano_backup_bundle import verify_portable_bundle
from core.organism_lab_persistence import OrganismLabStore

ACTIVE_SOURCE_ALIASES = (
    "CANO_DATABASE_URL", "DATABASE_URL", "MEMORY_DATABASE_URL",
    "QUEUE_DATABASE_URL", "CANO_MEMORY_DATABASE_URL",
    "CANO_QUEUE_DATABASE_URL",
)
_BAD_QUERY_KEYS = frozenset({
    "dbname", "database", "host", "hostaddr", "port", "service",
    "options", "passfile",
})
_STAGING_DB_PATTERN = re.compile(r"cano_restore_[A-Za-z0-9_]{1,47}\Z")


def _connection_identity(database_url: str) -> tuple[str, int, str]:
    """Refuse ambiguous URI overrides before any database connection.

    Recheck current_database() on the server as a second independent guard.
    """
    if not isinstance(database_url, str):
        raise ValueError("Database target is invalid")
    try:
        parts = urlsplit(database_url)
        if (parts.scheme not in ("postgres", "postgresql") or not parts.hostname
                or parts.fragment or not parts.path.startswith("/")):
            raise ValueError("Database target must be a PostgreSQL URI")
        pairs = parse_qsl(parts.query, keep_blank_values=True)
        if any(k in _BAD_QUERY_KEYS for k, _ in pairs):
            raise ValueError("Ambiguous database target parameters")
        dbname = unquote(parts.path[1:])
        if not dbname or "/" in dbname or "\\x00" in dbname:
            raise ValueError("Database name is invalid")
        return parts.hostname.lower(), parts.port or 5432, dbname
    except (ValueError, TypeError):
        raise ValueError("Database target URI is invalid") from None


def _verify_target(database_url: str) -> str:
    identity = _connection_identity(database_url)
    dbname = identity[2]
    if not _STAGING_DB_PATTERN.fullmatch(dbname):
        raise ValueError("Restore target must be a new cano_restore_* database")
    for alias in ACTIVE_SOURCE_ALIASES:
        source = os.environ.get(alias)
        if not source:
            continue
        source_identity = _connection_identity(source)
        # Fail closed even if the same database is exposed via a different
        # hostname or different credentials.
        if source_identity[2] == dbname or source_identity == identity:
            raise ValueError("Restore target matches an active source database")
    return dbname


def restore_lab_archive(
    ciphertext: bytes, passphrase: str, *,
    database_url: str, owner_key: str, connect=None,
) -> dict:
    """Authenticated, all-or-nothing laboratory recovery in staging only.

    Input owner identity is an operator-provided, verified staging OIDC HMAC key.
    It is intentionally not inferred from the archive or logged. In production,
    this is NOT an account import API; use only with a distinct staging DB.
    """
    dbname = _verify_target(database_url)
    # Verify ciphertext, all ZIP components and record digests BEFORE opening
    # any database connection or attempting any SQL.
    bundle = decrypt_backup(ciphertext, passphrase)
    files = verify_portable_bundle(bundle)
    if "organism-lab-records.json" not in files:
        raise ValueError("Legacy account backup has no laboratory history")
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    if (manifest.get("schema") != "cano-portable-backup-v2"
            or manifest.get("sources_available", {}).get("organism_lab") is not True):
        raise ValueError("Incomplete laboratory account backup")
    section = json.loads(files["organism-lab-records.json"].decode("utf-8"))
    records = section["records"]  # already validated by verify_portable_bundle
    if connect is None:
        import psycopg
        connect = psycopg.connect

    store = OrganismLabStore(owner_key, database_url, connect=connect)
    # The staging operator must be able to view the PHYSICAL table, not only
    # rows visible through RLS. SET LOCAL row_security=off fails closed for
    # restricted roles when RLS would hide another owner's records.
    with store._connection() as db, db.cursor() as cur:
        cur.execute("SELECT current_database()")
        row = cur.fetchone()
        if not row or row[0] != dbname:
            raise ValueError("Actual PostgreSQL target does not match isolated target")
        cur.execute("SELECT pg_advisory_xact_lock(%s)", (731136440,))
        cur.execute("SET LOCAL row_security = off")
        cur.execute("SELECT COUNT(*) FROM public.organism_lab_records")
        row = cur.fetchone()
        if not row or row[0] != 0:
            raise ValueError("Isolated laboratory target is not empty")
        for record in records:
            payload = json.dumps({
                "format": 1, "sha256": record["sha256"],
                "data_b64": record["data_b64"],
            }, separators=(",", ":"))
            cur.execute("""INSERT INTO public.organism_lab_records
                (owner_key, collection, record_id, payload)
                VALUES (%s, %s, %s, %s::jsonb)""", (
                store.owner_key, store.COLLECTION, record["record_id"], payload,
            ))
        # Any exception here aborts the transaction, with no partial restore.
    # Independent fresh connection, owner-scoped readback after commit.
    actual = store.export_for_backup()
    expected = sorted(records, key=lambda item: item["record_id"])
    if actual != expected:
        raise ValueError("Recovered laboratory records failed independent readback")
    return {
        "status": "ISOLATED_LAB_RESTORED",
        "restored_records": len(expected),
        "format": "cano-portable-backup-v2",
        "full_postgresql_restore": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Restore a local CANO v2 laboratory archive into a separate empty cano_restore_* PostgreSQL database.")
    parser.add_argument("encrypted_file", type=Path)
    parser.add_argument("--confirm-empty-isolated-target", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_empty_isolated_target:
        print("BLOCKED: explicitly confirm a new and isolated restore database", file=sys.stderr)
        return 2
    try:
        path = args.encrypted_file
        if path.is_symlink() or not path.is_file():
            raise ValueError("Encrypted account backup unavailable")
        if not (1 <= path.stat().st_size <= MAX_PLAINTEXT_BYTES + 128):
            raise ValueError("Encrypted account backup size invalid")
        database_url = os.environ["CANO_RESTORE_DATABASE_URL"]
        owner_key = os.environ["CANO_RESTORE_OWNER_KEY"]
        password = getpass("CANO archive password (local only): ")
        result = restore_lab_archive(
            path.read_bytes(), password, database_url=database_url, owner_key=owner_key)
    except (Exception) as _error:
        # Do not leak SQL messages, connection URIs, credentials or any JSON.
        print("BLOCKED: isolated laboratory restore or readback failed", file=sys.stderr)
        return 3
    print("PASS: isolated laboratory restore and new-connection readback verified; "
          + str(result["restored_records"]) + " records.")
    print("This does NOT verify a full PostgreSQL disaster-recovery backup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
