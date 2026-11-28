"""Optional transaction-bound owner proof for the PostgreSQL adapters.

Never use the database password as the signing key. Keys stay in the trusted
server environment and are separately provisioned per database login role.
The restrictive database policy remains the final fail-closed boundary.
"""
from collections.abc import Mapping
import hashlib
import hmac
import json
import os
import re

_ROLES = frozenset((
    "agent_task_app", "cano_runtime_rw", "cano_snapshot_app",
    "cano_snapshot_runtime", "memory_runtime_app", "organism_lab_runtime",
))

def set_owner_context(cur, owner_key, *, environment=None):
    env = os.environ if environment is None else environment
    mode = env.get("CANO_OWNER_PROOF_MODE", "off")
    if mode == "off":
        cur.execute("SELECT set_config('cano.owner_key', %s, true)", (owner_key,))
        return
    if mode != "required":
        raise PermissionError("Invalid owner proof mode")
    if not isinstance(owner_key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", owner_key):
        raise PermissionError("Invalid owner scope")
    cur.execute("SELECT current_user::text AS role_name, pg_current_xact_id()::text AS xact_id, pg_backend_pid()::text AS backend_pid")
    row = cur.fetchone()
    try:
        role, xid, pid = (row["role_name"], row["xact_id"], row["backend_pid"]) if isinstance(row, Mapping) else row
        if role not in _ROLES or not re.fullmatch(r"[0-9]+", str(xid)) or not re.fullmatch(r"[0-9]+", str(pid)):
            raise ValueError
        keys = json.loads(env.get("CANO_OWNER_PROOF_KEYS_JSON", ""))
        key = keys[role]
        if not isinstance(key, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", key):
            raise ValueError
        secret = bytes.fromhex(key)
    except (ValueError, TypeError, KeyError, AttributeError):
        raise PermissionError("Owner proof configuration unavailable") from None
    message = f"{role}:{owner_key}:{xid}:{pid}".encode("utf-8")
    proof = hmac.new(secret, message, hashlib.sha256).hexdigest()
    cur.execute("SELECT set_config('cano.owner_key', %s, true), set_config('cano.owner_proof', %s, true)", (owner_key, proof))
