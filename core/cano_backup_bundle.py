"""Create a single owner-scoped, portable CANO account backup archive."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import zlib
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from core.backup_encryption import MAX_PLAINTEXT_BYTES
from core.organism_lab_persistence import OrganismLabStore
from core.user_memory import export_library


MAX_COMPONENT_BYTES = 10 * 1024 * 1024
_ALLOWED_FILES = {
    "cano-colony.json", "memory-library.json", "research-tasks.json",
    "authorized-queue.json", "manifest.json",
}
_V2_FILES = _ALLOWED_FILES | {"organism-lab-records.json"}
_MAX_LAB_RECORDS = 1000


def _validate_organism_records(records: list) -> None:
    """Validate lab export items before encryption and after decryption."""
    if not isinstance(records, list) or len(records) > _MAX_LAB_RECORDS:
        raise ValueError("Organism Lab backup list exceeds its limit")
    seen = set()
    for item in records:
        if not isinstance(item, dict) or set(item) != {
            "record_id", "kind", "sha256", "data_b64"
        }:
            raise ValueError("Invalid Organism Lab backup record shape")
        kind, expected, record_id = (
            item["kind"], item["sha256"], item["record_id"])
        if kind not in ("world", "campaign") or not isinstance(expected, str):
            raise ValueError("Invalid Organism Lab backup record type")
        if not isinstance(record_id, str) or record_id in seen:
            raise ValueError("Invalid or duplicate Organism Lab backup identifier")
        seen.add(record_id)
        if record_id != f"cano-organism-lab-v1-{kind}-{expected}":
            raise ValueError("Organism Lab backup identifier checksum mismatch")
        encoded = item["data_b64"]
        if not isinstance(encoded, str):
            raise ValueError("Invalid Organism Lab backup data")
        try:
            raw = base64.b64decode(encoded, validate=True)
            document = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError, json.JSONDecodeError):
            raise ValueError("Invalid Organism Lab backup JSON") from None
        if len(raw) > OrganismLabStore.MAX_RECORD_BYTES:
            raise ValueError("Organism Lab backup record exceeds persistence size limit")
        if not isinstance(document, dict) or sha256(raw).hexdigest() != expected:
            raise ValueError("Organism Lab backup record checksum mismatch")




def _encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), default=str,
                      allow_nan=False).encode("utf-8")


def export_authorized_queue(queue) -> list[dict]:
    """Return the current authenticated owner's jobs and audit events only."""
    if queue is None:
        return []
    jobs = queue.list()
    if not isinstance(jobs, list) or len(jobs) > 1000:
        raise ValueError("Authorized queue export is invalid or exceeds its limit")
    result = []
    for raw in jobs:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise ValueError("Authorized queue export contains an invalid job")
        job = {key: value for key, value in raw.items()
               if key not in {"owner_key", "lease_token"}}
        events = queue.events(job["id"])
        if not isinstance(events, list):
            raise ValueError("Authorized queue audit export is invalid")
        job["events"] = events
        result.append(job)
    return result


def create_portable_bundle(*, colony, memories, research_tasks,
                           authorized_queue, organism_records=None) -> bytes:
    """Bundle only records already scoped to the signed-in owner/session.

    ``research_tasks`` and ``authorized_queue`` can be ``None`` when their
    stores are not configured. Queue lease secrets and owner identifiers are
    excluded; queue drafts and audit events are included for recovery.
    """
    if (not isinstance(colony, dict) or not all(
        isinstance(colony.get(key), list)
        for key in ("agents", "feedback", "reviews", "missions")
    )):
        raise ValueError("CANO colony snapshot is invalid")
    components = {
        "cano-colony.json": _encode(colony),
        "memory-library.json": export_library(memories if memories is not None else []).encode("utf-8"),
        "research-tasks.json": (research_tasks if isinstance(research_tasks, bytes)
                                else _encode({
                                    "schema": "research-task-export-v1",
                                    "available": research_tasks is not None,
                                    "tasks": research_tasks if research_tasks is not None else [],
                                })),
        "authorized-queue.json": _encode({
            "schema": "cano-authorized-queue-export-v1",
            "available": authorized_queue is not None,
            "jobs": authorized_queue if authorized_queue is not None else [],
        }),
    }
    if organism_records is not None:
        _validate_organism_records(organism_records)
        components["organism-lab-records.json"] = _encode({
            "schema": "cano-organism-lab-export-v1",
            "records": organism_records,
        })
    if any(len(data) > MAX_COMPONENT_BYTES for data in components.values()):
        raise ValueError("One CANO backup section exceeds the 10 MiB limit")
    manifest = {
        "schema": ("cano-portable-backup-v2" if organism_records is not None
                   else "cano-portable-backup-v1"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "warning": "Agent and model outputs are unverified drafts unless explicitly reviewed.",
        "sources_available": {
            "cano_colony": True,
            "memory_library": memories is not None,
            "research_tasks": research_tasks is not None,
            "authorized_queue": authorized_queue is not None,
            "organism_lab": organism_records is not None,
        },
        "components": {
            name: {"sha256": sha256(data).hexdigest(), "size_bytes": len(data)}
            for name, data in components.items()
        },
    }
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for name, data in components.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", _encode(manifest))
    result = output.getvalue()
    if not result or len(result) > MAX_PLAINTEXT_BYTES:
        raise ValueError("CANO portable backup exceeds the 20 MiB limit")
    return result


def verify_portable_bundle(bundle: bytes) -> dict[str, bytes]:
    """Validate a decrypted bundle before any caller writes or imports it."""
    if not isinstance(bundle, bytes) or not bundle or len(bundle) > MAX_PLAINTEXT_BYTES:
        raise ValueError("Portable backup size is invalid")
    try:
        with ZipFile(BytesIO(bundle), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) not in (
                    _ALLOWED_FILES, _V2_FILES):
                raise ValueError("Portable backup file list is invalid")
            if any(info.is_dir() or info.file_size > MAX_COMPONENT_BYTES
                   for info in infos):
                raise ValueError("Portable backup component exceeds its limit")
            files = {name: archive.read(name) for name in names}
    except (BadZipFile, OSError, RuntimeError, KeyError, EOFError, zlib.error):
        raise ValueError("Portable backup archive is damaged") from None
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError("Portable backup manifest is invalid") from None
    if not isinstance(manifest, dict):
        raise ValueError("Portable backup manifest is invalid")
    components = manifest.get("components")
    schema = manifest.get("schema")
    expected = (_ALLOWED_FILES if schema == "cano-portable-backup-v1"
                else _V2_FILES if schema == "cano-portable-backup-v2" else None)
    if expected is None or not isinstance(components, dict):
        raise ValueError("Portable backup manifest is unsupported")
    if set(files) != expected or set(components) != expected - {"manifest.json"}:
        raise ValueError("Portable backup manifest entries are invalid")
    if schema == "cano-portable-backup-v2":
        try:
            lab = json.loads(files["organism-lab-records.json"].decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise ValueError("Invalid Organism Lab backup JSON") from None
        if (not isinstance(lab, dict)
                or set(lab) != {"schema", "records"}
                or lab["schema"] != "cano-organism-lab-export-v1"):
            raise ValueError("Unsupported Organism Lab backup format")
        _validate_organism_records(lab["records"])
    for name, item in components.items():
        data = files[name]
        if (not isinstance(item, dict)
                or item.get("size_bytes") != len(data)
                or item.get("sha256") != sha256(data).hexdigest()):
            raise ValueError("Portable backup checksum mismatch")
    return files

