"""Render PG18 internal read-only connectivity probe, NEVER a backup/restore tool.

On process startup only, verify source identity with one metadata-only SELECT.
GET /healthz reports a fixed redacted result. No other action is exposed.
"""
from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.cano_pg_backup import _libpq_env_from_uri


def blocked(status="not_configured"):
    return {"status": status, "internal_readonly_verified": False,
            "source_rows_read": 0, "real_backup_created": False,
            "offsite_verified": False, "isolated_restore_verified": False}


def probe(environ=None, connect=None):
    env = dict(os.environ if environ is None else environ)
    uri = env.get("CANO_RENDER_INTERNAL_URL", "").strip()
    expected_db = env.get("CANO_REQUIRED_RENDER_DATABASE", "").strip()
    prefix = env.get("CANO_REQUIRED_RENDER_HOST_PREFIX", "").strip().lower()
    if (not uri or not re.fullmatch(r"[A-Za-z0-9_]+", expected_db)
            or not re.fullmatch(r"dpg-[a-z0-9-]+", prefix)):
        return blocked()
    try:
        pg = _libpq_env_from_uri(uri, env)
        host = pg["PGHOST"].lower().rstrip(".")
        if (pg["PGDATABASE"] != expected_db or
                not (host == prefix or
                     (host.startswith(prefix + ".") and host.endswith(".render.com")))):
            return blocked("identity_mismatch")
    except (KeyError, TypeError, ValueError):
        return blocked("invalid_source")

    try:
        if connect is None:
            from psycopg import connect
        with connect(uri, connect_timeout=5,
                     options="-c default_transaction_read_only=on") as db:
            row = db.execute(
                "SELECT current_database(), current_setting('server_version_num'), "
                "current_setting('transaction_read_only')").fetchone()
        if (not isinstance(row, (tuple, list)) or len(row) != 3
                or row[0] != expected_db or not str(row[1]).startswith("18")
                or row[2] != "on"):
            return blocked("server_identity_unverified")
    except Exception:
        # Never serialize exception: it might contain passwords or a URL.
        return blocked("connection_unverified")
    return {**blocked("pg18_readonly_connection_verified"),
            "internal_readonly_verified": True}


def serve(status, port):
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    body = json.dumps(status, sort_keys=True).encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass  # Never log user-supplied paths or query strings.

        def do_GET(self):
            if self.path != "/healthz":
                self.send_error(404)
                return
            self.send_response(200 if status["internal_readonly_verified"] else 503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            self.send_error(405)

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


def main():
    try:
        port = int(os.environ.get("PORT", "10000"))
        status = probe()  # exactly one attempt on startup, no row-level query
        serve(status, port)
    except (OSError, ValueError):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
