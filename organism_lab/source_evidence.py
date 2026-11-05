"""Offline source-evidence registry: strict provenance, deduplication and atomic export.

This module never fetches URLs or claims to have verified external source content.
"""
import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Evidence record must be an object")
    required = ("topic", "title", "source_url", "accessed_at", "claim", "assessment")
    if any(not isinstance(record.get(k), str) or not record[k].strip() for k in required):
        raise ValueError("Missing evidence fields")
    parsed = urlsplit(record["source_url"])
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Source URL must be a valid HTTPS URL")
    try:
        datetime.fromisoformat(record["accessed_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid ISO timestamp") from exc
    if record["assessment"] not in ("unverified", "supported", "contradicted", "uncertain"):
        raise ValueError("Unknown assessment")
    if record["assessment"] != "unverified" and not record.get("evidence_excerpt"):
        raise ValueError("Assessed claims require an evidence excerpt")
    canonical = {k: record[k] for k in required}
    if record.get("evidence_excerpt"):
        canonical["evidence_excerpt"] = record["evidence_excerpt"]
    return canonical


def compile_evidence(records):
    unique = {}
    for item in records:
        record = validate_record(item)
        identity = json.dumps([record["topic"], record["source_url"], record["claim"]],
                              ensure_ascii=False, separators=(",", ":"))
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if key in unique and unique[key] != record:
            raise ValueError("Conflicting duplicate evidence: " + key)
        unique[key] = record
    return {"schema": "source-evidence-v1", "count": len(unique),
            "records": [{"id": key, **unique[key]} for key in sorted(unique)]}


def export_evidence(source_json, destination_json):
    source_json = Path(source_json)
    destination_json = Path(destination_json)
    data = json.loads(source_json.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Input must be a JSON array")
    report = compile_evidence(data)
    destination_json.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=destination_json.parent, prefix=".evidence-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination_json)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return report
