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
import subprocess
import threading
import secrets
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import zipfile

from scripts.cano_encrypted_backup import make_encrypted_backup, verify_encrypted_backup, _child_env
from scripts.cano_pg_backup import BackupError, _libpq_env_from_uri
from scripts.cano_backup_source_gate import APP_SOURCE_PROFILES, require_application_source

_root = Path('/tmp/cano-owner-export')
_lock = threading.Lock()
_state = {'phase': 'idle', 'archive': '', 'receipt': '', 'size': 0, 'sha256': '', 'error': '',
          'offsite_phase': 'not_started', 'offsite_sha256': '', 'offsite_bytes': 0,
          'offsite_error': ''}
_SAFE_FAILURE_STAGES = frozenset({
    'configuration', 'source_inventory_query', 'source_inventory_empty',
    'application_scope', 'encrypted_export', 'archive_verification',
    'transfer_configuration', 'archive_package', 'archive_size',
    'archive_validation', 'upload_request', 'provider_confirmation',
})
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


def _source_table_count(*, environ=None, runner=subprocess.run) -> int:
    """Check the pinned source has real user tables before dumping.

    Read-only catalog metadata, not proof of complete CANO DB coverage.
    """
    env = os.environ if environ is None else environ
    if not source_verified(env):
        raise BackupError('Expected Render source identity not verified')
    exe = shutil.which('psql')
    if not exe:
        raise BackupError('PostgreSQL read-only source preflight unavailable')
    child_env = _child_env(_libpq_env_from_uri(env['CANO_RENDER_INTERNAL_URL'], env))
    sql = (
        "SELECT count(*) FROM pg_catalog.pg_class AS c "
        "JOIN pg_catalog.pg_namespace AS n ON c.relnamespace=n.oid "
        "WHERE c.relkind IN ('r','p') "
        "AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%' "
        "AND n.nspname NOT LIKE 'pg_temp_%'"
    )
    try:
        result = runner(
            [exe, '-X', '--no-password', '-At', '-v', 'ON_ERROR_STOP=1', '-c', sql],
            env=child_env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=30, check=False,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        raise BackupError('Read-only source table inventory failed') from None
    raw = getattr(result, 'stdout', None)
    if (getattr(result, 'returncode', None) != 0
            or not isinstance(raw, bytes) or len(raw) > 24
            or not raw.strip().isdigit()):
        raise BackupError('Read-only source table inventory failed')
    return int(raw.strip())


def _require_application_source(*, environ=None, runner=subprocess.run):
    """Fail closed unless the pinned Render DB contains the declared CANO scope.

    Reuses the already-tested canonical nine-table or scoped table profile.
    This is source inventory, NOT proof of live app ENV bindings or restore.
    """
    env = os.environ if environ is None else environ
    if not source_verified(env):
        raise BackupError('Pinned Render source is not verified')
    profile = env.get('CANO_REQUIRED_APPLICATION_PROFILE', '')
    if profile not in APP_SOURCE_PROFILES:
        raise BackupError('Explicit CANO application profile required')
    try:
        libpq = _libpq_env_from_uri(env['CANO_RENDER_INTERNAL_URL'], env)
        return require_application_source(
            libpq, profile,
            expected_host=libpq['PGHOST'].lower().rstrip('.'),
            expected_database=env['CANO_REQUIRED_RENDER_DATABASE'],
            psql_bin='psql', runner=runner, attest_counts=True,
        )
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        raise BackupError('Required CANO source inventory cannot be proven') from None


def _worker():
    # Keep diagnostics to a fixed, non-secret stage vocabulary. Provider and
    # libpq exception messages can contain connection details and are discarded.
    stage = 'configuration'
    try:
        if not configured():
            raise BackupError('Required owner-only configuration is missing')
        stage = 'source_inventory_query'
        source_tables = _source_table_count()
        if source_tables < 1:
            stage = 'source_inventory_empty'
            raise BackupError('No user tables at the pinned Render source')
        stage = 'application_scope'
        preflight = _require_application_source()
        stage = 'encrypted_export'
        _root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if _root.is_symlink():
            raise BackupError('Refusing linked staging directory')
        result = make_encrypted_backup(
            _root, database_env='CANO_RENDER_INTERNAL_URL',
            key_env='CANO_BACKUP_KEY_HEX', dump_bin='pg_dump',
            max_plaintext_bytes=256 * 1024 * 1024, max_seconds=480,
            source_preflight=preflight['source_preflight'])
        stage = 'archive_verification'
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
            _state.update(phase='failed', error=stage)



class _RejectUploadRedirect(HTTPRedirectHandler):
    """Never forward a short-lived Notion upload bearer through HTTP redirects."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The default urllib handler forwards Authorization to redirected hosts.
        # Return None so urllib raises an HTTP error rather than following it.
        return None


def _auto_upload_worker():
    """Optional one-time OFFSITE transfer using a short-lived Notion upload grant.

    The grant is configured privately via Render env vars, never in Git. The
    only upload bytes are a ZIP containing authenticated ciphertext and a
    receipt. The private AES key is never in the ZIP or network request.
    """
    stage = 'transfer_configuration'
    try:
        uri = os.environ.get('CANO_NOTION_UPLOAD_URL', '')
        auth = os.environ.get('CANO_NOTION_UPLOAD_AUTH', '')
        parsed = urlsplit(uri)
        if (parsed.scheme != 'https' or parsed.hostname != 'api.notion.com'
                or not parsed.path.startswith('/v1/mcp/file_uploads/')
                or not parsed.path.endswith('/send')
                or parsed.username or parsed.password or parsed.fragment
                or not auth.startswith('Bearer ') or len(auth) < 45):
            raise ValueError('Invalid one-time transfer configuration')
        with _lock:
            if _state['phase'] != 'idle':
                raise ValueError('Archive generation already started')
            _state.update(phase='running', offsite_phase='dumping', offsite_error='')
        stage = 'encrypted_export'
        _worker()
        with _lock:
            if _state['phase'] != 'ready':
                saved_stage = _state.get('error', '')
                stage = saved_stage if saved_stage in _SAFE_FAILURE_STAGES else 'encrypted_export'
                raise ValueError('Encrypted dump has not been verified')
            archive = Path(_state['archive'])
            receipt = Path(_state['receipt'])
            _state['offsite_phase'] = 'packaging'
        stage = 'archive_package'
        target = _root / 'CANO_RENDER_PG18_ENCRYPTED_BACKUP_20261112.zip'
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_STORED) as z:
            z.write(archive, arcname=archive.name)
            z.write(receipt, arcname=receipt.name)
            z.writestr('README.txt',
                       'CANO Render PostgreSQL 18 AUTHENTICATED ENCRYPTED EXPORT.\n'
                       'Contains only AES-256-GCM ciphertext and a verification receipt.\n'
                       'AES owner recovery key is NOT included.\n'
                       'Import requires separately retained owner key and isolated restore.\n')
        stage = 'archive_size'
        if target.stat().st_size > 19 * 1024 * 1024:
            raise ValueError('Exceeds supported one-part upload size')
        # Never upload a file unless ZIP CRC and every included hash passes.
        stage = 'archive_validation'
        with zipfile.ZipFile(target) as z:
            if z.testzip() is not None:
                raise ValueError('ZIP failed self-check')
        payload = target.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        boundary = '----cano-only-encrypted-' + secrets.token_hex(10)
        body = (('--' + boundary + '\r\n'
                 'Content-Disposition: form-data; name="file"; filename="' + target.name + '"\r\n'
                 'Content-Type: application/zip\r\n\r\n').encode()
                + payload + ('\r\n--' + boundary + '--\r\n').encode())
        stage = 'upload_request'
        req = Request(uri, data=body, method='POST', headers={
            'Authorization': auth,
            'Content-Type': 'multipart/form-data; boundary=' + boundary,
            'User-Agent': 'CANO-owner-encrypted-offsite/1',
        })
        with _lock:
            _state['offsite_phase'] = 'uploading'
        with build_opener(_RejectUploadRedirect()).open(req, timeout=75) as result:
            reply = result.read(8192)
            stage = 'provider_confirmation'
            parsed_reply = json.loads(reply)
            if result.status not in (200, 201) or parsed_reply.get('status') != 'uploaded':
                raise ValueError('Offsite provider did not confirm upload')
        with _lock:
            _state.update(offsite_phase='upload_http_accepted', offsite_error='',
                          offsite_sha256=digest, offsite_bytes=len(payload))
    except Exception:
        # Never serialize a provider URL, token, database URL or internal error.
        with _lock:
            _state.update(offsite_phase='failed',
                          offsite_error=stage if stage in _SAFE_FAILURE_STAGES else 'transfer_configuration')



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
            with _lock:
                offsite = {k: _state[k] for k in ('offsite_phase', 'offsite_sha256', 'offsite_bytes', 'offsite_error')}
            return self._json(200, {'service': 'cano-encrypted-export', 'api': 'owner_only', **offsite})
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
        if os.environ.get('CANO_AUTO_UPLOAD_ONCE') == '1':
            threading.Thread(target=_auto_upload_worker, daemon=True, name='cano-offsite-upload-once').start()
        ThreadingHTTPServer(('0.0.0.0', port), Handler).serve_forever()
    except (OSError, ValueError):
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
