"""Read-only CANO task DB preflight; never return credentials or exception text."""
from __future__ import annotations
import re

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
        etype = type(exc).__name__
        if etype not in {"OperationalError", "ProgrammingError", "PermissionError",
                         "DatabaseNotConfigured", "InsufficientPrivilege",
                         "UndefinedTable", "UndefinedColumn", "InvalidPassword",
                         "InterfaceError", "ValueError", "KeyError"}:
            etype = "OtherDatabaseError"
        raw_code = getattr(exc, "sqlstate", None)
        code = raw_code if isinstance(raw_code, str) and re.fullmatch(r"[A-Z0-9]{5}", raw_code) else None
        return {"ok": False, "reason": "connection_or_schema", "error_type": etype, "sqlstate": code}
    return {"ok": True, "reason": "verified"}
