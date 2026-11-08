"""Offline, read-only audit of CANO password-protected account exports.

Does NOT connect to Postgres, print secrets, unpack user records to disk, or
assert that a portable account export is a full pg_dump disaster-recovery copy.

Run: python scripts/cano_account_backup_audit.py <path-to-.canoenc>
Password is requested locally with getpass; never pass it as a command argument.
"""
from __future__ import annotations

import argparse
import base64
from getpass import getpass
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import zlib
from zipfile import BadZipFile, ZipFile

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"CANOENC1"
SALT_BYTES = 16
NONCE_BYTES = 12
HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES
TAG_BYTES = 16
MAX_PLAINTEXT_BYTES = 20 * 1024 * 1024
MAX_COMPONENT_BYTES = 10 * 1024 * 1024
COMPONENTS_V1 = frozenset({"cano-colony.json", "memory-library.json", "research-tasks.json", "authorized-queue.json"})
COMPONENTS_V2 = COMPONENTS_V1 | {"organism-lab-records.json"}
REQUIRED_SOURCES = ("cano_colony", "memory_library", "research_tasks", "authorized_queue", "organism_lab")
HEX_SHA = re.compile(r"^[a-f0-9]{64}$")

class AuditError(ValueError):
    """Expected invalid/unverifiable export. Messages never contain user data."""


def _decrypt(ciphertext: bytes, passphrase: str) -> bytes:
    if not isinstance(ciphertext, bytes) or not (HEADER_BYTES + TAG_BYTES <= len(ciphertext) <= MAX_PLAINTEXT_BYTES + HEADER_BYTES + TAG_BYTES):
        raise AuditError("Encrypted file size is invalid or exceeds 20 MiB")
    if not ciphertext.startswith(MAGIC):
        raise AuditError("Unsupported CANO account backup format")
    if not isinstance(passphrase, str) or not (12 <= len(passphrase) <= 1024):
        raise AuditError("A local passphrase of 12-1024 characters is required")
    salt = ciphertext[len(MAGIC):len(MAGIC) + SALT_BYTES]
    nonce = ciphertext[len(MAGIC) + SALT_BYTES:HEADER_BYTES]
    header = ciphertext[:HEADER_BYTES]
    try:
        key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))
        plaintext = AESGCM(key).decrypt(nonce, ciphertext[HEADER_BYTES:], header)
    except (InvalidTag, ValueError, UnicodeError):
        raise AuditError("Invalid passphrase, corrupted archive, or unsupported encrypted backup type") from None
    if len(plaintext) > MAX_PLAINTEXT_BYTES:
        raise AuditError("Decrypted archive exceeds 20 MiB")
    return plaintext


def _json(data: bytes, label: str):
    try:
        return json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise AuditError("Invalid JSON in " + label) from None


def _check_lab(data: bytes) -> int:
    obj = _json(data, "organism-lab")
    if not isinstance(obj, dict) or set(obj) != {"schema", "records"} or obj["schema"] != "cano-organism-lab-export-v1":
        raise AuditError("Unsupported organism-lab section")
    records = obj["records"]
    if not isinstance(records, list) or len(records) > 1000:
        raise AuditError("Invalid organism-lab record count")
    seen = set()
    for obj in records:
        if not isinstance(obj, dict) or set(obj) != {"record_id", "kind", "sha256", "data_b64"}:
            raise AuditError("Invalid organism-lab record shape")
        kind, identifier, digest, encoded = obj["kind"], obj["record_id"], obj["sha256"], obj["data_b64"]
        if kind not in ("world", "campaign") or not isinstance(digest, str) or not HEX_SHA.fullmatch(digest):
            raise AuditError("Invalid organism-lab record metadata")
        if not isinstance(identifier, str) or identifier != f"cano-organism-lab-v1-{kind}-{digest}" or identifier in seen:
            raise AuditError("Invalid organism-lab record identifier")
        seen.add(identifier)
        if not isinstance(encoded, str):
            raise AuditError("Invalid organism-lab encoding")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error):
            raise AuditError("Invalid organism-lab encoding") from None
        if len(raw) > 1_000_000 or sha256(raw).hexdigest() != digest or not isinstance(_json(raw, "organism-lab record"), dict):
            raise AuditError("Invalid organism-lab record hash or structure")
    return len(records)


def audit_export(ciphertext: bytes, passphrase: str) -> dict:
    plaintext = _decrypt(ciphertext, passphrase)
    try:
        with ZipFile(BytesIO(plaintext), "r") as archive:
            infos = archive.infolist()
            names = [i.filename for i in infos]
            name_set = set(names)
            if len(names) != len(name_set) or len(names) not in (5, 6) or "manifest.json" not in name_set:
                raise AuditError("Invalid archive entries or duplicate filenames")
            if any(i.is_dir() or i.file_size > MAX_COMPONENT_BYTES or i.file_size < 0 for i in infos):
                raise AuditError("Invalid or oversized backup section")
            if sum(i.file_size for i in infos) > MAX_PLAINTEXT_BYTES:
                raise AuditError("Backup sections exceed allowed uncompressed size")
            files = {name: archive.read(name) for name in names}
    except (BadZipFile, OSError, RuntimeError, EOFError, KeyError, zlib.error, NotImplementedError):
        raise AuditError("Damaged or unreadable ZIP content") from None
    manifest = _json(files["manifest.json"], "manifest")
    if not isinstance(manifest, dict):
        raise AuditError("Invalid manifest object")
    schema = manifest.get("schema")
    expected = {"cano-portable-backup-v1": COMPONENTS_V1,
                "cano-portable-backup-v2": COMPONENTS_V2}.get(schema)
    if expected is None or name_set != expected | {"manifest.json"}:
        raise AuditError("Unsupported or incomplete archive section list")
    entries = manifest.get("components")
    if not isinstance(entries, dict) or set(entries) != expected:
        raise AuditError("Manifest section inventory is incomplete")
    for name, meta in entries.items():
        data = files[name]
        if (not isinstance(meta, dict) or meta.get("size_bytes") != len(data)
                or meta.get("sha256") != sha256(data).hexdigest()):
            raise AuditError("Backup section integrity mismatch")
        _json(data, name)
    sources = manifest.get("sources_available")
    if not isinstance(sources, dict) or not all(type(sources.get(n)) is bool for n in REQUIRED_SOURCES):
        raise AuditError("Missing or invalid source availability evidence")
    if schema == "cano-portable-backup-v2":
        lab_count = _check_lab(files["organism-lab-records.json"])
    else:
        lab_count = None
    colony = _json(files["cano-colony.json"], "cano-colony.json")
    if not isinstance(colony, dict) or not all(isinstance(colony.get(k), list) for k in ("agents", "feedback", "reviews", "missions")):
        raise AuditError("Invalid colony snapshot")
    missing = [k for k in REQUIRED_SOURCES if sources.get(k) is not True]
    if schema == "cano-portable-backup-v1" and "organism_lab" not in missing:
        missing.append("organism_lab")
    # Regardless of account-bundle coverage, snapshot REVISION history and SQL
    # schema belong to a separate, full PostgreSQL dump and restore check.
    complete_owner_scope = not missing and schema == "cano-portable-backup-v2"
    return {
        "format": schema,
        "encrypted_container_sha256": sha256(ciphertext).hexdigest(),
        "zip_manifest_and_section_digests_verified": True,
        "owner_bundle_sections_verified": len(expected),
        "owner_scope_sections_all_available": complete_owner_scope,
        "missing_owner_scope_sections": sorted(set(missing)),
        "organism_lab_records_in_export": lab_count,
        "colony_agents_in_export": len(colony["agents"]),
        "colony_missions_in_export": len(colony["missions"]),
        "postgres_sql_schema_included": False,
        "postgres_revision_history_included": False,
        "full_postgresql_disaster_recovery": False,
        "status": "OWNER_SCOPE_READY_NOT_FULL_PG" if complete_owner_scope else "OWNER_SCOPE_PARTIAL",
        "next_action": "Separately verify a full encrypted pg_dump restored into an isolated empty PostgreSQL database"
    }


def main(argv=None) -> int:
    args = argparse.ArgumentParser(description="Offline verification of CANO encrypted account downloads; never a full PostgreSQL backup")
    args.add_argument("file", type=Path, help="Locally downloaded cano-hesap-yedegi.canoenc")
    ns = args.parse_args(argv)
    try:
        if ns.file.is_symlink() or not ns.file.is_file():
            raise AuditError("Backup path must be an existing regular file, not a symlink")
        if not (HEADER_BYTES + TAG_BYTES <= ns.file.stat().st_size <= MAX_PLAINTEXT_BYTES + HEADER_BYTES + TAG_BYTES):
            raise AuditError("Encrypted file size invalid or exceeds the 20 MiB account-backup limit")
        pw = getpass("CANO yedek parolası (yalnızca bu bilgisayarda): ")
        data = ns.file.read_bytes()
        result = audit_export(data, pw)
        print(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False))
        return 0 if result["owner_scope_sections_all_available"] else 2
    except (AuditError, OSError):
        print("CANO audit blocked: invalid, inaccessible, incomplete or unverifiable export", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
