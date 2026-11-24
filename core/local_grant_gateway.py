"""Bounded WSGI entry point; TLS scheme must come from a trusted proxy.

Run behind an HTTPS reverse proxy on a private listener only. The WSGI
server/proxy must independently bound headers, request time and body sizes.
A disabled gateway never opens a database.
"""
from collections import deque
from threading import Lock, BoundedSemaphore
from time import monotonic
from http import HTTPStatus
import os

from core.local_grant_http import make_app
from core.local_task_handoff import encode_file
from core.postgres_local_grant import PostgresLocalGrant

def create_gateway(environment, *, store=None, max_per_minute=30):
    if type(max_per_minute) is not int or not 1 <= max_per_minute <= 120:
        raise ValueError("Invalid rate limit")
    enabled = environment.get("CANO_LOCAL_GRANT_ENABLED") == "1"
    if enabled and store is None:
        url = environment.get("AGENT_TASK_DATABASE_URL")
        if not url:
            raise RuntimeError("Gateway database configuration unavailable")
        store = PostgresLocalGrant(url)
    inner = make_app(store) if enabled else None
    history = deque()
    lock = Lock()
    slots = BoundedSemaphore(2)

    def application(env, start_response):
        def reject(code, error):
            body = encode_file({"error": error})
            start_response(f"{code} {HTTPStatus(code).phrase}", [
                ("Content-Type","application/json"),("Cache-Control","no-store"),
                ("Content-Length",str(len(body)))])
            return [body]
        if inner is None:
            return reject(503,"disabled")
        # Never trust a raw request's X-Forwarded-Proto field here.
        if env.get("wsgi.url_scheme") != "https":
            return reject(403,"https_required")
        with lock:
            now=monotonic()
            while history and history[0] <= now-60:
                history.popleft()
            if len(history) >= max_per_minute:
                return reject(429,"rate_limited")
            history.append(now)
        if not slots.acquire(blocking=False):
            return reject(503,"busy")
        try:
            return inner(env,start_response)
        finally:
            slots.release()
    return application

def from_environment():
    return create_gateway(os.environ)
