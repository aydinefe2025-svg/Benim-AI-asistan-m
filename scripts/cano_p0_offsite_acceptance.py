"""Owner-operated CANO P0 acceptance: REAL offsite GET -> authenticated ciphertext -> isolated PG18 restore -> parity.

This does not run a backup or make a remote store. It closes a restore acceptance
only after the existing encrypted backup tools and a separate trusted storage
provider have actually been used. All credentials and the signed download URL
are environment-only; no plaintext, database URL, or token is logged.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import unquote, urlsplit
from urllib.request import build_opener, HTTPRedirectHandler

from scripts.cano_encrypted_backup import (
    BackupError, restore_to_empty_database, verify_encrypted_backup,
)

SOURCE_PROJECT = "sweet-sound-73776160"
SOURCE_DB = "assistant_pg"
RECOVERY_SCHEMA = "cano_p0_neon_recovery_20261115"
RECOVERY_TABLES = (
    "agent_research_drafts", "agent_research_task_events", "agent_research_tasks",
    "cano_authorized_job_events", "cano_authorized_jobs", "organism_lab_records",
    "private_colony_snapshot_revisions", "private_colony_snapshots",
    "private_memory_entries",
)
PUBLIC_TABLES = (*RECOVERY_TABLES, "cano_code_jobs")
TABLES = tuple(sorted(
    [(RECOVERY_SCHEMA, name) for name in RECOVERY_TABLES] +
    [("public", name) for name in PUBLIC_TABLES]
))
ALLOWED_SUFFIXES = (".amazonaws.com", ".notion.com", ".notion.so", ".storage.googleapis.com", "storage.googleapis.com")
EARLIEST_BACKUP = datetime(2026, 11, 22, tzinfo=timezone.utc)


class AcceptanceBlocked(RuntimeError):
    """Safe, nonsecret reason for refusing an incomplete recovery."""


def _identity(url: str) -> tuple[str, str, int]:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        db = unquote(parsed.path[1:])
        port = parsed.port or 5432
        if parsed.scheme not in ("postgres", "postgresql") or not host or not db:
            raise ValueError("incomplete")
        return host, db, port
    except (ValueError, TypeError):
        raise AcceptanceBlocked("database_identity_unverified") from None


def _safe_download_url(raw: str, pinned_host: str) -> str:
    try:
        url = urlsplit(raw)
        host = (url.hostname or "").lower().rstrip(".")
        pin = pinned_host.lower().rstrip(".")
        allowed = (host == "storage.googleapis.com"
                   or any(host.endswith(suffix) for suffix in ALLOWED_SUFFIXES))
        if (url.scheme != "https" or not allowed or not host or host != pin
                or url.username or url.password or url.fragment
                or url.port not in (None, 443)):
            raise AcceptanceBlocked("offsite_host_not_allowed")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass  # Public DNS name, not a raw IP address.
        else:
            raise AcceptanceBlocked("offsite_host_not_allowed")
    except (TypeError, ValueError):
        raise AcceptanceBlocked("offsite_host_not_allowed") from None
    return host


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None  # Signed one-file URL must be direct; no cross-host relay.


def _secure_open(url: str):
    return build_opener(_NoRedirect).open(url, timeout=60)


def _download_ciphertext(raw_url: str, pinned_host: str, destination: Path,
                         expected_length: int, expected_sha: str) -> int:
    host = _safe_download_url(raw_url, pinned_host)
    digest = hashlib.sha256()
    total = 0
    try:
        with _secure_open(raw_url) as response:
            if (getattr(response, "status", None) != 200
                    or _safe_download_url(response.geturl(), host) != host):
                raise AcceptanceBlocked("offsite_response_unverified")
            with destination.open("xb") as output:
                os.chmod(destination, 0o600)
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > expected_length:
                        raise AcceptanceBlocked("offsite_ciphertext_mismatch")
                    digest.update(chunk)
                    output.write(chunk)
    except AcceptanceBlocked:
        raise
    except (OSError, ValueError):
        raise AcceptanceBlocked("offsite_download_failed") from None
    if total != expected_length or digest.hexdigest() != expected_sha:
        raise AcceptanceBlocked("offsite_ciphertext_mismatch")
    return total


def _inventory(dsn: str) -> dict:
    # Read-only, repeatable snapshot; PostgreSQL never sends private row content.
    import psycopg
    result = {}
    with psycopg.connect(dsn, connect_timeout=15) as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL TIME ZONE 'UTC'")
        rows = connection.execute("""
            SELECT table_schema,table_name FROM information_schema.tables
            WHERE table_type='BASE TABLE'
              AND table_schema IN ('public','cano_p0_neon_recovery_20261115')
        """).fetchall()
        if set(rows) != set(TABLES):
            raise AcceptanceBlocked("table_coverage_mismatch")
        for schema, table in TABLES:
            # Identifiers are constants, never taken from users or a receipt.
            statement = (
                'SELECT count(*)::bigint,md5(coalesce(string_agg('
                'md5(to_jsonb(t)::text),\',\' ORDER BY md5(to_jsonb(t)::text)),\'\')) '
                f'FROM "{schema}"."{table}" AS t'
            )
            n, digest = connection.execute(statement).fetchone()
            result[f"{schema}.{table}"] = (int(n), digest)
    return result


def _server_major(dsn: str) -> int:
    import psycopg
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        return int(conn.execute("SHOW server_version_num").fetchone()[0]) // 10000


def accept(*, receipt: Path, min_rows: int = 119) -> dict:
    """Check actual evidence in a trusted owner environment; fail before production writes."""
    src = os.environ.get("DATABASE_URL", "")
    dst = os.environ.get("CANO_RESTORE_DATABASE_URL", "")
    expected_host = os.environ.get("CANO_BACKUP_EXPECTED_HOST", "").lower().rstrip(".")
    expected_db = os.environ.get("CANO_BACKUP_EXPECTED_DB", "")
    host, database, port = _identity(src)
    dest_host, dest_database, dest_port = _identity(dst)
    if (not expected_host or host != expected_host or database != SOURCE_DB
            or expected_db != SOURCE_DB or host.endswith(".render.com")
            or (host, database, port) == (dest_host, dest_database, dest_port)
            or not dest_database.startswith("cano_restore_")):
        raise AcceptanceBlocked("source_or_target_identity_unverified")
    if _server_major(dst) != 18:
        raise AcceptanceBlocked("isolated_target_not_pg18")

    try:
        proof = verify_encrypted_backup(receipt)
        metadata = json.loads(Path(receipt).read_text(encoding="utf-8"))
        created = datetime.fromisoformat(metadata["created_utc"].replace("Z", "+00:00"))
    except (BackupError, OSError, ValueError, KeyError, TypeError):
        raise AcceptanceBlocked("archive_authentication_failed") from None
    preflight = metadata.get("application_source_preflight") or {}
    if (not proof.get("authenticated") or not proof.get("receipt_authenticated")
            or not proof.get("source_preflight_metadata_authenticated")
            or preflight.get("profile") != "full"
            or preflight.get("required_tables_matched") != 9
            or not preflight.get("nonempty_table_verified")
            or not preflight.get("source_host_pinned")
            or not preflight.get("source_database_pinned")
            or created.tzinfo is None or created < EARLIEST_BACKUP):
        raise AcceptanceBlocked("signed_current_source_proof_missing")

    original = Path(receipt).parent / metadata["archive"]
    if original.is_symlink() or not original.is_file():
        raise AcceptanceBlocked("archive_authentication_failed")
    actual_length = metadata.get("archive_size_bytes")
    archive_hash = metadata.get("archive_sha256")
    if (type(actual_length) is not int or actual_length <= 36
            or not isinstance(archive_hash, str) or len(archive_hash) != 64):
        raise AcceptanceBlocked("archive_authentication_failed")
    original_inventory = _inventory(src)
    if sum(n for n, _ in original_inventory.values()) < min_rows:
        raise AcceptanceBlocked("source_rows_below_baseline")

    raw_url = os.environ.get("CANO_OFFSITE_DOWNLOAD_URL", "")
    pin = os.environ.get("CANO_OFFSITE_DOWNLOAD_HOST", "")
    if not raw_url or not pin:
        raise AcceptanceBlocked("offsite_download_not_configured")
    if pin.lower().rstrip(".") in (host, dest_host):
        raise AcceptanceBlocked("offsite_host_not_allowed")

    with tempfile.TemporaryDirectory(prefix="cano-p0-cipher-only-") as root:
        downloaded = Path(root) / "redownloaded.canoenc"
        byte_count = _download_ciphertext(raw_url, pin, downloaded,
                                          actual_length, archive_hash)
        restore = restore_to_empty_database(
            downloaded, target_db_url_env="CANO_RESTORE_DATABASE_URL", confirm=True
        )
        if (restore.get("authenticated") is not True
                or restore.get("restored_to_new_database") is not True
                or restore.get("plaintext_sha256") != proof.get("plaintext_sha256")):
            raise AcceptanceBlocked("isolated_restore_unverified")
        restored_inventory = _inventory(dst)
        # Source must not have changed while the recovery test was underway.
        after_inventory = _inventory(src)
        if original_inventory != restored_inventory or after_inventory != original_inventory:
            raise AcceptanceBlocked("source_restore_parity_mismatch")

    return {
        "status": "PASS",
        "scope": "owner-local validated offsite GET and isolated PG18 restore",
        "source_database": SOURCE_DB,
        "expected_source_project": SOURCE_PROJECT,
        "source_pg_major": _server_major(src),
        "target_pg_major": 18,
        "table_count": len(TABLES),
        "row_count": sum(n for n, _ in original_inventory.values()),
        "offsite_redownload_bytes": byte_count,
        "same_ciphertext_sha256": archive_hash,
        "authenticated_archive": True,
        "signed_receipt": True,
        "isolated_restore": True,
        "all_table_content_parity": True,
        "live_app_environment_mapping_independently_verified": False,
        "render_pg18_source_backed_up": False,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Owner-only P0 recovery acceptance; no secrets in argv")
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(accept(receipt=args.receipt), sort_keys=True))
        return 0
    except Exception:
        # Sensitive exceptions, DSNs, remote signed URLs and private rows never printed.
        print('BLOCKED: independent offsite-to-empty-PG18 acceptance not proven')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
