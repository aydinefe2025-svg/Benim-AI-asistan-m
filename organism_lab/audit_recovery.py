"""Read-only assessment of an interrupted or corrupted audit chain.

Never edits, truncates, or automatically trusts the damaged source file.
"""
import hashlib
import json
from pathlib import Path
from .audit_store import _canonical


def assess_audit(path):
    file = Path(path)
    if not file.exists():
        return {"status": "missing", "valid_records": 0, "first_bad_line": None,
                "valid_prefix": [], "source_unchanged": True}
    raw = file.read_bytes()
    lines = raw.splitlines(keepends=True)
    previous = "0" * 64
    valid = []
    bad = None
    reason = None
    for number, line in enumerate(lines, 1):
        if not line.endswith(b"\n"):
            bad, reason = number, "incomplete_line"
            break
        try:
            record = json.loads(line.decode("utf-8"))
            if not isinstance(record, dict):
                raise ValueError("Invalid record shape")
            digest = record.get("digest")
            payload = {k: v for k, v in record.items() if k != "digest"}
            expected = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
            if payload.get("previous") != previous or digest != expected:
                raise ValueError("Digest chain mismatch")
        except (UnicodeError, ValueError, TypeError) as exc:
            bad, reason = number, type(exc).__name__
            break
        valid.append(record)
        previous = digest
    return {"status": "damaged" if bad else "intact", "valid_records": len(valid),
            "first_bad_line": bad, "reason": reason, "valid_prefix": valid,
            "source_unchanged": True}
