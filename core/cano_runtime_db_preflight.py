"""Read-only CANO database preflights; never return credentials or exception text."""
from __future__ import annotations

import re


_SAFE_ERROR_TYPES = {
    "OperationalError", "ProgrammingError", "PermissionError",
    "DatabaseNotConfigured", "InsufficientPrivilege", "UndefinedTable",
    "UndefinedColumn", "InvalidPassword", "InterfaceError", "ValueError",
    "KeyError",
}


def _safe_failure(exc):
    error_type = type(exc).__name__
    if error_type not in _SAFE_ERROR_TYPES:
        error_type = "OtherDatabaseError"
    raw_code = getattr(exc, "sqlstate", None)
    code = raw_code if isinstance(raw_code, str) and re.fullmatch(r"[A-Z0-9]{5}", raw_code) else None
    return {
        "ok": False,
        "reason": "connection_or_schema",
        "error_type": error_type,
        "sqlstate": code,
    }


def preflight_task_store(db_url, *, store_factory=None):
    if not isinstance(db_url, str) or not db_url.strip():
        return {"ok": False, "reason": "not_configured"}
    if store_factory is None:
        from core.postgres_task_store import PostgresTaskStore
        store_factory = PostgresTaskStore
    try:
        store = store_factory(database_url=db_url, owner_key="read_only_preflight")
        store.verify_schema()
    except Exception as exc:
        return _safe_failure(exc)
    return {"ok": True, "reason": "verified"}


def preflight_authorized_queue(db_url, *, queue_factory=None):
    """Verify queue schema/privileges using only identity and LIMIT 0 SELECTs."""
    if not isinstance(db_url, str) or not db_url.strip():
        return {"ok": False, "reason": "not_configured"}
    if queue_factory is None:
        from core.postgres_authorized_queue import PostgresAuthorizedQueue
        queue_factory = PostgresAuthorizedQueue
    try:
        queue = queue_factory(database_url=db_url, owner_key="read_only_preflight")
        queue.verify_schema()
    except Exception as exc:
        return _safe_failure(exc)
    return {"ok": True, "reason": "verified"}
