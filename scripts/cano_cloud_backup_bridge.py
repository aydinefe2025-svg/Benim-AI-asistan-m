"""Owner-only read/download bridge for a real encrypted Render PG18 backup.

No database rows or raw dump are served. Backup runs once on startup only when
explicitly armed by owner. The only downloadable bytes are AES-GCM ciphertext,
behind constant-time bearer authentication. Never publish token or AES key.
"""
from __future__ import annotations
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

from scripts.cano_cloud_readonly_probe import probe
from scripts.cano_encrypted_backup import make_encrypted_backup

ROOT = Path(__file__).resolve().parent.parent
BIN = ROOT / ".cano-pg18" / "pg_dump18"
DEST = ROOT / ".cano-render-rescue-ciphertext"
MAX_RANGE = 8 * 1024 * 1024


def authorized(header: str | None, token: str) -> bool:
    if not token or len(token) != 64 or not re.fullmatch(r"[0-9a-f]{64}", token):
        return False
    if not isinstance(header, str) or not re.fullmatch(r"Bearer [0-9a-f]{64}", header):
        return False
    return hmac.compare_digest(header[7:], token)


def parse_range(value: str | None, total: int) -> tuple[int, int]:
    """Return inclusive bounded range; strict parser prevents unbounded reads."""
    if not isinstance(total, int) or not 0 < total <= 2 * 1024**3:
        raise ValueError("archive size invalid")
    if value is None:
        return (0, min(total, MAX_RANGE) - 1)
    match = re.fullmatch(r"bytes=([0-9]{1,12})-([0-9]{0,12})", value)
    if not match:
        raise ValueError("unsupported Range")
    start = int(match.group(1))
    end = min(total - 1, start + MAX_RANGE - 1)
    if match.group(2):
        end = min(end, int(match.group(2)))
    if start > end or start >= total:
        raise ValueError("out of bounds Range")
    return start, end


class RescueState:
    def __init__(self, source: dict[str, Any]):
        self.source = source
        self.lock = threading.Lock()
        self.backup_state = "disabled"
        self.archive: Path | None = None
        self.receipt: Path | None = None

    def health(self) -> dict[str, Any]:
        with self.lock:
            phase = self.backup_state
        result = {**self.source,
                  "backup_state": phase,
                  "real_backup_created": phase == "ready",
                  "offsite_verified": False,
                  "isolated_restore_verified": False}
        if phase != "disabled":
            result.pop("source_rows_read", None)  # pg_dump may read real rows
        return result

    def artifact(self, kind: str) -> Path | None:
        with self.lock:
            if self.backup_state != "ready":
                return None
            return self.archive if kind == "archive" else self.receipt

    def run_once(self) -> None:
        with self.lock:
            self.backup_state = "running"
        try:
            result = make_encrypted_backup(
                DEST, database_env="CANO_RENDER_INTERNAL_URL",
                key_env="CANO_BACKUP_KEY_HEX", dump_bin=str(BIN),
                max_plaintext_bytes=1024**3, max_seconds=900)
            archive = Path(result["archive"])
            receipt = Path(result["receipt"])
            if (not archive.is_file() or not receipt.is_file()
                    or file_sha256(archive) != result["archive_sha256"]):
                raise ValueError("archive readback mismatch")
            with self.lock:
                self.archive, self.receipt, self.backup_state = archive, receipt, "ready"
        except Exception:
            # Do not log exceptions: they can contain credentials or a URL.
            with self.lock:
                self.backup_state = "failed"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for part in iter(lambda: fh.read(256 * 1024), b""):
            digest.update(part)
    return digest.hexdigest()


def handler_for(state: RescueState, owner_token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CANO"
        sys_version = ""
        def log_message(self, *args):
            pass
        def _headers(self, status, *, length, mime="application/json", additional=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if additional:
                for k, v in additional.items():
                    self.send_header(k, v)
            self.end_headers()
        def do_GET(self):
            if self.path == "/healthz":
                body = json.dumps(state.health(), sort_keys=True).encode("utf-8")
                self._headers(200 if state.source.get("internal_readonly_verified") else 503,
                              length=len(body))
                self.wfile.write(body)
                return
            if self.path not in ("/owner/receipt", "/owner/archive") or not authorized(self.headers.get("Authorization"), owner_token):
                self.send_error(404)
                return
            kind = "receipt" if self.path.endswith("receipt") else "archive"
            src = state.artifact(kind)
            if src is None or not src.is_file() or src.is_symlink():
                self.send_error(503)
                return
            size = src.stat().st_size
            if kind == "receipt":
                if size > 65536:
                    self.send_error(503)
                    return
                with src.open("rb") as stream:
                    body = stream.read()
                self._headers(200, length=len(body))
                self.wfile.write(body)
                return
            try:
                begin, end = parse_range(self.headers.get("Range"), size)
            except ValueError:
                self.send_error(416)
                return
            count = end - begin + 1
            extra = {"Accept-Ranges": "bytes", "Content-Range": f"bytes {begin}-{end}/{size}"}
            self._headers(206, length=count, mime="application/octet-stream", additional=extra)
            try:
                with src.open("rb") as stream:
                    stream.seek(begin)
                    remaining = count
                    while remaining:
                        chunk = stream.read(min(256 * 1024, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (ConnectionError, BrokenPipeError, OSError):
                pass
        def do_POST(self):
            self.send_error(405)
    return Handler


def main() -> int:
    source = probe()  # verifies expected Render PG18, DB name and read-only mode
    state = RescueState(source)
    owner_token = os.environ.get("CANO_BACKUP_TRANSFER_TOKEN", "")
    enabled = os.environ.get("CANO_RESCUE_ENABLE") == "1"
    if enabled and source.get("internal_readonly_verified") and len(owner_token) == 64:
        thread = threading.Thread(target=state.run_once, daemon=True, name="cano-one-shot-backup")
        thread.start()
    port = int(os.environ.get("PORT", "10000"))
    if port < 1 or port > 65535:
        return 1
    ThreadingHTTPServer(("0.0.0.0", port), handler_for(state, owner_token)).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())