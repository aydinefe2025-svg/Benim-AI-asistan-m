"""Operator-only encrypted rescue of all explicitly configured CANO Postgres URLs.

Runs on the owner's private persistent machine, NOT on Render free web disk.
Uses the existing audited streaming AES-256-GCM PostgreSQL backup implementation.
Never exports secrets, DB URLs or rows in logs/receipts. No network changes,
database writes, automatic migration, restore or third-party upload.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path

from scripts.cano_pg_backup import _libpq_env_from_uri
from scripts.cano_encrypted_backup import (
    BackupError, _key, _private_directory, _private_receipt,
    make_encrypted_backup, verify_encrypted_backup,
)

SOURCE_ENV_NAMES = (
    "CANO_DATABASE_URL",
    "DATABASE_URL",
    "MEMORY_DATABASE_URL",
    "AGENT_TASK_DATABASE_URL",
)


def backup_configured(destination: Path) -> dict:
    """Encrypt and independently verify each *configured* source, exactly once.

    Two aliases are deduplicated only if their complete URLs are identical.
    Even the database hostname and username are excluded from the manifest.
    The result is LOCAL encrypted evidence, not proof of offsite durability
    or a successful restore.
    """
    if os.environ.get("RENDER_SERVICE_ID"):
        raise BackupError("Refusing an ephemeral Render service as backup destination")
    _key()  # Validate key before touching the filesystem.
    render_db = os.environ.get("CANO_REQUIRED_RENDER_DATABASE", "").strip()
    render_host_prefix = os.environ.get("CANO_REQUIRED_RENDER_HOST_PREFIX", "").strip().lower()
    identity_required = ("CANO_REQUIRED_RENDER_DATABASE" in os.environ
                         or "CANO_REQUIRED_RENDER_HOST_PREFIX" in os.environ)
    if identity_required and (
            not re.fullmatch(r"[A-Za-z0-9_]+", render_db)
            or not re.fullmatch(r"dpg-[a-z0-9-]+", render_host_prefix)):
        raise BackupError("The expected Render source identity is incomplete or invalid")

    required_source_matched = False
    matched_render_urls: set[str] = set()
    groups: dict[str, list[str]] = {}
    for env_name in SOURCE_ENV_NAMES:
        url = os.environ.get(env_name, "").strip()
        if url:
            # Validate *all* endpoints before producing partial backups.
            parsed = _libpq_env_from_uri(url, os.environ)
            hostname = parsed["PGHOST"].lower().rstrip(".")
            is_render_hostname = (
                hostname == render_host_prefix
                or (hostname.startswith(render_host_prefix + ".")
                    and hostname.endswith(".render.com")))
            if identity_required and (
                    parsed["PGDATABASE"] == render_db and is_render_hostname):
                required_source_matched = True
                matched_render_urls.add(url)
            groups.setdefault(url, []).append(env_name)
    if not groups:
        raise BackupError("No configured PostgreSQL sources to back up")
    if identity_required and not required_source_matched:
        raise BackupError("Expected Render database source was not configured")

    destination = Path(destination)
    if destination.is_symlink():
        raise BackupError("Private backup destination must not be a symlink")
    if destination.exists():
        if not destination.is_dir():
            raise BackupError("Private backup destination is not a directory")
        if any(destination.iterdir()):
            raise BackupError("Use a fresh empty private backup directory")
    _private_directory(destination)

    manifest_entries = []
    matched_source_numbers = []
    for ordinal, (_url, env_names) in enumerate(groups.items(), start=1):
        folder = destination / f"source-{ordinal:02d}"
        result = make_encrypted_backup(folder, database_env=env_names[0])
        archive = Path(result["archive"])
        receipt = Path(result["receipt"])
        if (archive.parent.resolve() != folder.resolve()
                or receipt.parent.resolve() != folder.resolve()
                or archive.name in ("", ".", "..")
                or receipt.name in ("", ".", "..")):
            raise BackupError("Encrypted backup returned an unsafe archive path")
        proof = verify_encrypted_backup(receipt)
        if (proof.get("authenticated") is not True
                or proof.get("archive_sha256") != result.get("archive_sha256")):
            raise BackupError("Authenticated backup readback mismatch")
        if _url in matched_render_urls:
            matched_source_numbers.append(ordinal)
        manifest_entries.append({
            "source_number": ordinal,
            "env_aliases": env_names,
            "archive": f"source-{ordinal:02d}/{archive.name}",
            "receipt": f"source-{ordinal:02d}/{receipt.name}",
            "archive_sha256": proof["archive_sha256"],
            "authenticated_readback": True,
        })

    manifest = destination / "cano-rescue-manifest.json"
    covered = [name for names in groups.values() for name in names]
    # Preserve the stable source-variable order, not the group interleaving.
    covered = [name for name in SOURCE_ENV_NAMES if name in covered]
    payload = {
        "format": "cano-operator-encrypted-multisource-v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "verified_source_count": len(manifest_entries),
        "covered_env_names": covered,
        "entries": manifest_entries,
        "local_authenticated_readback": True,
        "required_render_source_matched": required_source_matched,
        "required_render_source_numbers": matched_source_numbers,
        "offsite_verified": False,
        "isolated_restore_verified": False,
        "coverage_limit": "Configured URLs only; discover all other provider DBs separately.",
    }
    _private_receipt(manifest, payload)
    return {
        "manifest": str(manifest),
        "verified_source_count": len(manifest_entries),
        "covered_env_names": covered,
        "required_render_source_matched": required_source_matched,
        "required_render_source_numbers": matched_source_numbers,
        "offsite_verified": False,
        "isolated_restore_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Encrypted owner-only backups of all configured CANO PostgreSQL URLs"
    )
    parser.add_argument("private_destination", type=Path)
    args = parser.parse_args()
    try:
        result = backup_configured(args.private_destination)
    except (BackupError, OSError, ValueError, KeyError, TypeError):
        # Do not put connection strings, raw subprocess stderr or secrets on stdout.
        print("ERROR: multi-source encrypted backup failed; inspect private configuration")
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
