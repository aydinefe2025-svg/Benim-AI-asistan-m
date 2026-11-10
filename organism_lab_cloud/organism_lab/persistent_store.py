"""Tenant-scoped Postgres archive for the hosted Organism Lab.

The database schema is managed by reviewed migrations; this module never runs DDL.
Only an authenticated OIDC issuer/subject pair can be converted to an owner key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import json
import os
import re
import gzip
import tarfile
from contextlib import contextmanager
from pathlib import Path, PurePosixPath


class PersistenceNotConfigured(RuntimeError):
    pass


class PersistenceConflict(RuntimeError):
    pass


def _field(user, name):
    if isinstance(user, dict):
        return user.get(name)
    try:
        return getattr(user, name)
    except (AttributeError, KeyError):
        return None


def authenticated_owner_key(user, *, allowed_email: str, secret: str) -> str:
    """Return a stable opaque tenant ID only for the configured verified owner."""
    if _field(user, "is_logged_in") is not True:
        raise PermissionError("Authentication required")
    email = _field(user, "email")
    verified = _field(user, "email_verified")
    issuer, subject = _field(user, "iss"), _field(user, "sub")
    if (not isinstance(email, str) or not isinstance(allowed_email, str)
            or email.casefold().strip() != allowed_email.casefold().strip()
            or verified not in (True, "true", "True")
            or not isinstance(issuer, str) or not issuer.startswith("https://")
            or not isinstance(subject, str) or not subject
            or not isinstance(secret, str) or len(secret.encode("utf-8")) < 32):
        raise PermissionError("Verified owner identity is required")
    message = (issuer + "\0" + subject).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def pack_directory(root: str | Path, *, max_file_bytes=16 * 1024 * 1024,
                   max_total_bytes=64 * 1024 * 1024) -> bytes:
    """Create a deterministic, bounded archive of regular app data files."""
    root = Path(root).resolve()
    buffer = io.BytesIO()
    total = 0
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_symlink() or not path.is_file() or path.name.endswith(("-wal", "-shm")):
                    continue
                resolved = path.resolve()
                if root not in resolved.parents:
                    raise ValueError("Archive path escapes the user directory")
                size = path.stat().st_size
                total += size
                if size > max_file_bytes or total > max_total_bytes:
                    raise ValueError("Archive size limit exceeded")
                relative = path.relative_to(root).as_posix()
                info = tarfile.TarInfo(relative)
                info.size = size
                info.mtime = 0
                info.mode = 0o600
                with path.open("rb") as source:
                    archive.addfile(info, source)
    result = buffer.getvalue()
    if len(result) > max_total_bytes:
        raise ValueError("Compressed archive size limit exceeded")
    return result


def unpack_directory(data: bytes, root: str | Path, *, max_file_bytes=16 * 1024 * 1024,
                     max_total_bytes=64 * 1024 * 1024) -> None:
    """Restore only bounded regular files; reject traversal and links."""
    if not isinstance(data, bytes) or len(data) > max_total_bytes:
        raise ValueError("Invalid archive size")
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        members = archive.getmembers()
        total = 0
        for member in members:
            relative = PurePosixPath(member.name)
            if (relative.is_absolute() or not relative.parts or ".." in relative.parts
                    or not member.isfile() or member.issym() or member.islnk()):
                raise ValueError("Unsafe archive member")
            total += member.size
            if member.size > max_file_bytes or total > max_total_bytes:
                raise ValueError("Archive size limit exceeded")
        for member in members:
            target = (root / Path(*PurePosixPath(member.name).parts)).resolve()
            if root not in target.parents:
                raise ValueError("Archive path escapes the user directory")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError("Invalid archive member")
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".restore-tmp")
            with temporary.open("wb") as output:
                output.write(source.read(max_file_bytes + 1))
            temporary.replace(target)


class PostgresArchive:
    """A single-owner, compare-and-swap archive using the reviewed table."""
    COLLECTION = "simulation"
    RECORD_ID = "filesystem_snapshot_v1"

    def __init__(self, owner_key: str, database_url: str | None = None, *, connect=None):
        if not re.fullmatch(r"[0-9a-f]{64}", owner_key or ""):
            raise ValueError("Invalid owner key")
        self.owner_key = owner_key
        self.database_url = database_url or os.environ.get("DATABASE_URL")
        if not self.database_url:
            raise PersistenceNotConfigured("DATABASE_URL is required")
        if connect is None:
            import psycopg
            connect = psycopg.connect
        self._connect = connect

    @contextmanager
    def _connection(self):
        """Set the transaction-local RLS identity before any archive query."""
        with self._connect(self.database_url, connect_timeout=8) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('organism.owner_key', %s, true)",
                            (self.owner_key,))
            yield conn

    def check(self):
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1 FROM public.organism_lab_records LIMIT 0")

    def load(self):
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute("""SELECT payload FROM public.organism_lab_records
                WHERE owner_key=%s AND collection=%s AND record_id=%s""",
                (self.owner_key, self.COLLECTION, self.RECORD_ID))
            row = cur.fetchone()
        if row is None:
            return None, None
        payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        raw = base64.b64decode(payload["data_b64"], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if not hmac.compare_digest(digest, payload.get("sha256", "")):
            raise ValueError("Archive integrity check failed")
        return raw, digest

    def save(self, data: bytes, *, expected_digest: str | None) -> str:
        digest = hashlib.sha256(data).hexdigest()
        payload = json.dumps({"format": 1, "sha256": digest,
                              "data_b64": base64.b64encode(data).decode("ascii")},
                             separators=(",", ":"))
        with self._connection() as conn, conn.cursor() as cur:
            if expected_digest is None:
                cur.execute("""INSERT INTO public.organism_lab_records
                    (owner_key, collection, record_id, payload)
                    VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING
                    RETURNING record_id""",
                    (self.owner_key, self.COLLECTION, self.RECORD_ID, payload))
            else:
                cur.execute("""INSERT INTO public.organism_lab_records
                    (owner_key, collection, record_id, payload)
                    VALUES (%s,%s,%s,%s::jsonb)
                    ON CONFLICT (owner_key, collection, record_id) DO UPDATE
                    SET payload=EXCLUDED.payload, updated_at=now()
                    WHERE public.organism_lab_records.payload->>'sha256'=%s
                    RETURNING record_id""",
                    (self.owner_key, self.COLLECTION, self.RECORD_ID, payload, expected_digest))
            if cur.fetchone() is None:
                raise PersistenceConflict("A newer archive exists; this save was not applied")
        return digest


def snapshot_json(data: bytes) -> dict:
    """Return a download-safe envelope without exposing database credentials."""
    return {"format": 1, "sha256": hashlib.sha256(data).hexdigest(),
            "data_b64": base64.b64encode(data).decode("ascii")}


def restore_snapshot_json(value: dict, root: str | Path) -> None:
    if not isinstance(value, dict) or value.get("format") != 1:
        raise ValueError("Unsupported backup format")
    data = base64.b64decode(value.get("data_b64", ""), validate=True)
    digest = hashlib.sha256(data).hexdigest()
    if not hmac.compare_digest(digest, value.get("sha256", "")):
        raise ValueError("Backup integrity check failed")
    unpack_directory(data, root)

