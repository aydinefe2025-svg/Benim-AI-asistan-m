"""Explicit single-attempt local task handoff; server retains the lease.

File hashes detect corruption, not the authenticity of a model or its claims.
The authenticated owner session and the queue's server-clock lease authorize
result import. No owner key, lease token, DB credentials or endpoint in a ticket.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import secrets
import sqlite3
import time
from pathlib import Path
from contextlib import closing

TICKET_SCHEMA = "cano-local-task-v1"
RESULT_SCHEMA = "cano-local-result-v1"
MAX_FILE_BYTES = 65536
_TICKET_KEYS = {"schema", "job_id", "nonce", "goal", "expires_at", "ticket_sha256"}
_RESULT_KEYS = {"schema", "job_id", "nonce", "ticket_sha256", "draft", "draft_sha256"}


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _hex(value, length):
    return isinstance(value, str) and bool(re.fullmatch("[0-9a-f]{%d}" % length, value))


def validate_ticket(ticket):
    if not isinstance(ticket, dict) or set(ticket) != _TICKET_KEYS:
        raise ValueError("Invalid local ticket fields")
    expiry = ticket["expires_at"]
    if (ticket["schema"] != TICKET_SCHEMA or not _hex(ticket["job_id"], 32)
            or not _hex(ticket["nonce"], 32) or not _hex(ticket["ticket_sha256"], 64)
            or not isinstance(ticket["goal"], str) or not ticket["goal"].strip()
            or len(ticket["goal"]) > 1200 or type(expiry) not in (int, float)
            or not math.isfinite(expiry)):
        raise ValueError("Invalid local ticket")
    body = {k: v for k, v in ticket.items() if k != "ticket_sha256"}
    if not secrets.compare_digest(_hash(_json(body)), ticket["ticket_sha256"]):
        raise ValueError("Local ticket digest mismatch")
    return ticket


def claim_ticket(queue, *, approved=False):
    if approved is not True:
        raise PermissionError("Explicit local handoff authorization required")
    job = queue.claim("local-file-handoff", approved=True, lease_seconds=3600)
    if job is None:
        return None
    ticket = {"schema": TICKET_SCHEMA, "job_id": job["id"],
              "nonce": secrets.token_hex(16), "goal": job["goal"],
              "expires_at": job["lease_until"]}
    ticket["ticket_sha256"] = _hash(_json(ticket))
    validate_ticket(ticket)
    return {"owner_key": queue.owner_key, "lease_token": job["lease_token"],
            "ticket": ticket}


def _validate_result(ticket, result):
    validate_ticket(ticket)
    if not isinstance(result, dict) or set(result) != _RESULT_KEYS:
        raise ValueError("Invalid local result fields")
    if (result["schema"] != RESULT_SCHEMA
            or any(result[k] != ticket[k] for k in ("job_id", "nonce", "ticket_sha256"))
            or not isinstance(result["draft"], str)
            or not result["draft"].strip() or result["draft"] != result["draft"].strip()
            or len(result["draft"]) > 12000
            or not _hex(result["draft_sha256"], 64)
            or not secrets.compare_digest(_hash(result["draft"]), result["draft_sha256"])):
        raise ValueError("Local result does not match the ticket")


def run_ticket(ticket, ledger_path, answer, *, approved=False):
    if approved is not True:
        raise PermissionError("Explicit local model authorization required")
    validate_ticket(ticket)
    if not callable(answer):
        raise ValueError("Local model callback required")
    if time.time() >= ticket["expires_at"]:
        raise PermissionError("Local ticket expired")
    path = Path(ledger_path)
    if path.is_symlink():
        raise ValueError("Local ledger must not be a symbolic link")
    key = ticket["nonce"]
    digest = ticket["ticket_sha256"]
    with closing(sqlite3.connect(path, timeout=15)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS handoff_attempts(
            nonce TEXT PRIMARY KEY, ticket_sha256 TEXT NOT NULL,
            result TEXT)""")
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT ticket_sha256,result FROM handoff_attempts WHERE nonce=?",
                         (key,)).fetchone()
        if row:
            if row[0] != digest or row[1] is None:
                raise RuntimeError("Prior attempt uncertain or conflicting; do not replay")
            result = json.loads(row[1])
            _validate_result(ticket, result)
            return result
        # Commit the attempt before any model call. A crash/failed call cannot
        # automatically run again; the server lease must be reconciled.
        db.execute("INSERT INTO handoff_attempts VALUES(?,?,NULL)", (key, digest))
    draft = answer(ticket["goal"])
    if not isinstance(draft, str) or not draft.strip() or len(draft.strip()) > 12000:
        raise ValueError("Invalid local draft")
    draft = draft.strip()
    result = {"schema": RESULT_SCHEMA, "job_id": ticket["job_id"], "nonce": key,
              "ticket_sha256": digest, "draft": draft, "draft_sha256": _hash(draft)}
    _validate_result(ticket, result)
    with closing(sqlite3.connect(path, timeout=15)) as db, db:
        cur = db.execute("UPDATE handoff_attempts SET result=? WHERE nonce=? AND "
                         "ticket_sha256=? AND result IS NULL", (_json(result), key, digest))
        if cur.rowcount != 1:
            raise RuntimeError("Local result write uncertain")
    return result


def accept_result(queue, private, result, *, approved=False):
    if approved is not True:
        raise PermissionError("Explicit import authorization required")
    if not isinstance(private, dict) or private.get("owner_key") != queue.owner_key:
        raise PermissionError("Ticket does not belong to this authenticated owner")
    ticket = private["ticket"]
    _validate_result(ticket, result)
    job = queue.get(ticket["job_id"])
    if job.get("state") == "review_pending":
        if job.get("result_digest") != result["draft_sha256"] or job.get("draft") != result["draft"]:
            raise PermissionError("Existing result differs; manual review required")
    else:
        queue.complete(ticket["job_id"], private["lease_token"], result["draft"])
        job = queue.get(ticket["job_id"])
    if (job.get("state") != "review_pending"
            or job.get("result_digest") != result["draft_sha256"]
            or job.get("draft") != result["draft"]):
        raise RuntimeError("Queue readback not verified; do not replay")
    return {"id": ticket["job_id"], "status": "review_pending", "verified": False,
            "readback": True}


def parse_file(data):
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_FILE_BYTES:
        raise ValueError("Local transfer file size invalid")
    return json.loads(data.decode("utf-8"))


def encode_file(value):
    raw = _json(value).encode("utf-8")
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Local transfer file too large")
    return raw
