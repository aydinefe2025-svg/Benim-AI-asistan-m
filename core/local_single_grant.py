"""One explicitly delegated task; in-memory prototype, not a production API.

The authenticated server keeps the owner identity and queue lease. A random
bearer capability authorizes exactly one ticket retrieval and its result only.
Restart/revocation fail closed; no general queue or shell access.
"""
import hashlib
import secrets
import threading
import time
from copy import deepcopy
from core.local_task_handoff import validate_ticket, accept_result


class SingleTaskGrant:
    def __init__(self, queue, private, digest):
        self._queue = queue
        self._private = deepcopy(private)
        self._digest = digest
        self._lock = threading.Lock()
        self._taken = False
        self._revoked = False

    @classmethod
    def issue(cls, queue, private, *, approved=False):
        if approved is not True or private.get("owner_key") != queue.owner_key:
            raise PermissionError("Explicit authenticated delegation required")
        ticket = validate_ticket(private["ticket"])
        if time.time() >= ticket["expires_at"]:
            raise PermissionError("Ticket expired")
        if queue.get(ticket["job_id"])["state"] != "running":
            raise PermissionError("Task is not leased")
        token = secrets.token_urlsafe(32)
        return cls(queue, private, hashlib.sha256(token.encode("ascii")).digest()), token

    def _authorize(self, token):
        if not isinstance(token, str) or len(token) != 43 or not token.isascii():
            raise PermissionError("Invalid grant")
        if (self._revoked or time.time() >= self._private["ticket"]["expires_at"]
                or not secrets.compare_digest(hashlib.sha256(token.encode("ascii")).digest(),
                                              self._digest)):
            raise PermissionError("Invalid or expired grant")

    def take(self, token):
        with self._lock:
            self._authorize(token)
            if self._taken:
                raise PermissionError("Already delegated; no automatic replay")
            self._taken = True
            return deepcopy(self._private["ticket"])

    def finish(self, token, result):
        with self._lock:
            self._authorize(token)
            if not self._taken:
                raise PermissionError("Ticket has not been delegated")
            return accept_result(self._queue, self._private, result, approved=True)

    def revoke(self):
        with self._lock:
            self._revoked = True
