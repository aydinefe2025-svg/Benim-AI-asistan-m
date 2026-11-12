"""Owner-only, one-shot, encrypted Render PG18 backup bridge.

Staging on the Render free web-service filesystem is EPHEMERAL and is never
considered a durable backup. Client must copy and verify ciphertext off-Render.
No row data or database credentials are returned to HTTP clients or logs.
"""
from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import threading
from urllib.parse import urlsplit

from scripts.cano_encrypted_backup import make_encrypted_backup, verify_encrypted_backup
from scripts.cano_pg_backup import BackupError, _libpq_env_from_uri

_root = Path('/tmp/cano-owner-export')
_lock = threading.Lock()
_state = {'phase': 'idle', 'archive': '', 'receipt': '', 'size': 0, 'sha256': '', 'error': ''}
_ALLOWED_PHASES = ('idle', 'running', 'ready', 'failed', 'purged')


def source_verified(environ=None):
    """Fail closed on source identity *before* executing pg_dump."""
    env = os.environ if environ is None else environ
    uri = env.get('CANO_RENDER_INTERNAL_URL', '')
    expected_db = env.get('CANO_REQUIRED_RENDER_DATABASE', '')
    prefix = env.get('CANO_REQUIRED_RENDER_HOST_PREFIX', '').lower()
    if not (re.fullmatch(r'[A-Za-z0-9_]+', expected_db or '')
            and re.fullmatch(r'dpg-[a-z0-9-]+', prefix or '')):
        return False
    try:
        pg = _libpq_env_from_uri(uri, env)
        host = pg['PGHOST'].lower().rstrip('.')
        return (pg['PGDATABASE'] == expected_db and
                (host == prefix or (host.startswith(prefix + '.') and host.endswith('.render.com'))))
    except (BackupError, ValueError, KeyError, TypeError):
        return False


def valid_auth(value, token=None):
    token = os.environ.get('CANO_EXPORT_ACCESS_TOKEN', '') if token is None else token
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        return False
    if not isinstance(value, str) or not value.startswith('Bearer '):
        return False
    return hmac.compare_digest(value[7:].encode(), token.encode())


def configured():
    return (source_verified() and
            re.fullmatch(r'[a-f0-9]{64}', os.environ.get('CANO_BACKUP_KEY_HEX', '')) is not None and
            valid_auth('Bearer ' + os.environ.get('CANO_EXPORT_ACCESS_TOKEN', '')))


def _worker():
    try:
        if not configured():
            raise BackupError('Required owner-only configuration is missing')
        _root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if _root.is_symlink():
            raise BackupError('Refusing linked staging directory')
        result = make_encrypted_backup(
            _root, database_env='CANO_RENDER_INTERNAL_URL',
            key_env='CANO_BACKUP_KEY_HEX', dump_bin='pg_dump',
            max_plaintext_bytes=256 * 1024 * 1024, max_seconds=480)
        archive = Path(result['archive'])
        receipt = Path(result['receipt'])
        proof = verify_encrypted_backup(receipt)
        if (proof['archive_sha256'] != result['archive_sha256']
                or archive.stat().st_size != result['size_bytes']):
            raise BackupError('Encrypted archive verification did not match')
        with _lock:
            _state.update(phase='ready', archive=str(archive), receipt=str(receipt),
                          size=result['size_bytes'], sha256=result['archive_sha256'])
    except Exception:
        # Never print exceptions; some error strings contain a connection URI.
        with _lock:
            _state.update(phase='failed', error='export_or_verification_failed')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *_args):
        pass

    def _json(self, status, obj):
        raw = json.dumps(obj, separators=(',', ':'), sort_keys=True).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        if not valid_auth(self.headers.get('Authorization', '')):
            self._json(401, {'status': 'unauthorized'})
            return False
        return True

    def do_POST(self):
        if not self._authorized():
            return
        length = self.headers.get('Content-Length', '0')
        if length != '0':
            return self._json(400, {'status': 'no_request_body_allowed'})
        if self.path == '/v1/start':
            with _lock:
                if _state['phase'] != 'idle':
                    return self._json(409, {'phase': _state['phase']})
                if not configured():
                    return self._json(503, {'phase': 'unconfigured'})
                _state['phase'] = 'running'
            threading.Thread(target=_worker, daemon=True, name='cano-encrypted-export').start()
            return self._json(202, {'phase': 'running'})
        if self.path == '/v1/purge':
            with _lock:
                if _state['phase'] != 'ready':
                    return self._json(409, {'phase': _state['phase']})
                paths = (_state['archive'], _state['receipt'])
                _state.update(phase='purged', archive='', receipt='')
            for p in paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass
            return self._json(200, {'phase': 'purged'})
        return self._json(404, {'status': 'not_found'})

    def do_GET(self):
        if self.path == '/healthz':
            return self._json(200, {'service': 'cano-encrypted-export', 'api': 'owner_only'})
        if not self._authorized():
            return
        if self.path == '/v1/status':
            with _lock:
                snap = dict(_state)
            return self._json(200, {key: snap[key] for key in ('phase', 'size', 'sha256', 'error')})
        if self.path == '/v1/receipt':
            with _lock:
                phase, receipt = _state['phase'], _state['receipt']
            if phase != 'ready':
                return self._json(409, {'phase': phase})
            try:
                d = json.loads(Path(receipt).read_text('utf-8'))
                safe_keys = ('format', 'archive', 'archive_size_bytes', 'archive_sha256',
                             'plaintext_size_bytes', 'plaintext_sha256', 'encrypted', 'authenticated')
                return self._json(200, {k: d[k] for k in safe_keys})
            except Exception:
                return self._json(503, {'phase': 'receipt_unavailable'})
        if self.path == '/v1/archive':
            with _lock:
                phase, name, size, sha = (_state[k] for k in ('phase', 'archive', 'size', 'sha256'))
            if phase != 'ready':
                return self._json(409, {'phase': phase})
            path = Path(name)
            try:
                if path.is_symlink() or path.parent != _root or path.stat().st_size != size:
                    return self._json(503, {'phase': 'archive_unavailable'})
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Disposition', 'attachment; filename="cano-render-pg18.canoenc"')
                self.send_header('X-Archive-SHA256', sha)
                self.send_header('Content-Length', str(size))
                self.end_headers()
                with path.open('rb') as source:
                    while True:
                        part = source.read(128 * 1024)
                        if not part:
                            break
                        self.wfile.write(part)
            except (ConnectionError, BrokenPipeError, OSError):
                return
            return
        return self._json(404, {'status': 'not_found'})


def main():
    try:
        port = int(os.environ.get('PORT', '10000'))
        if not 1 <= port <= 65535:
            raise ValueError('invalid port')
        ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
    except (OSError, ValueError):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
