"""Private manual backups for CANO's expiring Render PostgreSQL instance.

No database connection occurs on import. No automatic scheduling, restore,
or external upload. Secret connection URLs never appear in subprocess argv,
stdout, receipts, or exception messages.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import uuid
from urllib.parse import parse_qsl, unquote, urlsplit


class BackupError(RuntimeError):
    """An intentionally secret-free operational failure."""


# Environment parameter names supported by PostgreSQL 17 libpq; URL query
# parameters not in this allowlist are rejected rather than silently ignored.
_LIBPQ_URI_OPTIONS = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslcrl": "PGSSLCRL",
    "sslcrldir": "PGSSLCRLDIR",
    "sslcertmode": "PGSSLCERTMODE",
    "sslnegotiation": "PGSSLNEGOTIATION",
    "sslsni": "PGSSLSNI",
    "ssl_min_protocol_version": "PGSSLMINPROTOCOLVERSION",
    "ssl_max_protocol_version": "PGSSLMAXPROTOCOLVERSION",
    "channel_binding": "PGCHANNELBINDING",
    "require_auth": "PGREQUIREAUTH",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "application_name": "PGAPPNAME",
    "options": "PGOPTIONS",
    "hostaddr": "PGHOSTADDR",
    "gssencmode": "PGGSSENCMODE",
    "krbsrvname": "PGKRBSRVNAME",
    "gsslib": "PGGSSLIB",
    "gssdelegation": "PGGSSDELEGATION",
    "sslcompression": "PGSSLCOMPRESSION",
    "requirepeer": "PGREQUIREPEER",
    "client_encoding": "PGCLIENTENCODING",
    "load_balance_hosts": "PGLOADBALANCEHOSTS",
}

# A caller's inherited PGHOST/PGDATABASE/PGSERVICE settings must not
# silently redirect a backup away from the requested connection URI.
_LIBPQ_CONNECTION_VARS = frozenset({
    "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
    "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGHOSTADDR",
    *_LIBPQ_URI_OPTIONS.values(),
})


def _libpq_connection_env(database_url: str) -> dict[str, str]:
    """Convert a PostgreSQL URI into libpq parameter environment variables.

    The PGDATABASE environment variable accepts a database NAME, not the
    complete URI in the same way that pg_dump's --dbname argument does.
    Never put credentials into subprocess argv, error output or receipts.
    """
    try:
        parts = urlsplit(database_url)
        if (parts.scheme not in ("postgres", "postgresql")
                or not parts.hostname or parts.username is None
                or parts.path in ("", "/") or parts.fragment):
            raise ValueError("Invalid PostgreSQL URI")
        port = parts.port
        result = {
            "PGHOST": parts.hostname,
            "PGPORT": str(port or 5432),
            "PGDATABASE": unquote(parts.path[1:]),
            "PGUSER": unquote(parts.username),
        }
        if parts.password is not None:
            result["PGPASSWORD"] = unquote(parts.password)
        seen = set()
        for key, value in parse_qsl(parts.query, keep_blank_values=True,
                                    strict_parsing=True):
            if key not in _LIBPQ_URI_OPTIONS or key in seen or not value:
                raise ValueError("Unsupported or duplicate PostgreSQL URI option")
            seen.add(key)
            result[_LIBPQ_URI_OPTIONS[key]] = value
        return result
    except (ValueError, UnicodeError):
        raise BackupError("Invalid or unsupported PostgreSQL connection URL") from None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check_binary(name: str) -> str:
    result = shutil.which(name)
    if not result:
        raise BackupError(f"Required executable not found: {name}")
    return result


def _archive_is_valid(path: Path, *, restore_bin: str = "pg_restore") -> None:
    # This checks archive parsing, not whether a real restore would succeed.
    if not path.is_file() or path.stat().st_size < 6:
        raise BackupError("Backup file is missing or empty")
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise BackupError("Not a PostgreSQL custom-format archive")
    exe = _check_binary(restore_bin)
    try:
        result = subprocess.run(
            [exe, "--list", str(path)], capture_output=True, timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise BackupError("pg_restore archive inspection failed") from None
    if result.returncode != 0 or not result.stdout.strip():
        raise BackupError("pg_restore could not inspect the archive")


def _private_json(path: Path, payload: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".cano-receipt-", dir=str(path.parent))
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, sort_keys=True, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def make_backup(destination: Path, *, database_env: str = "DATABASE_URL",
                dump_bin: str = "pg_dump", restore_bin: str = "pg_restore") -> dict:
    # Render free web service disks are ephemeral: destination MUST be an
    # independently persistent user-controlled device/volume, not Render /tmp.
    database_url = os.environ.get(database_env, "")
    if not database_url or not database_url.startswith(("postgres://", "postgresql://")):
        raise BackupError(f"Expected PostgreSQL connection URL in {database_env}")
    connection_env = _libpq_connection_env(database_url)
    dump_exe = _check_binary(dump_bin)
    _check_binary(restore_bin)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    if destination.is_symlink():
        raise BackupError("Backup directory cannot be a symlink")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    basename = f"cano-postgres-{stamp}-{uuid.uuid4().hex[:12]}"
    archive = destination / (basename + ".dump")
    receipt = destination / (basename + ".receipt.json")
    fd, temporary = tempfile.mkstemp(prefix=".cano-pgdump-", dir=str(destination))
    os.close(fd)
    os.chmod(temporary, 0o600)
    try:
        env = os.environ.copy()
        # Explicitly remove the original URL and inherited libpq routing
        # options, then provide only parsed libpq values to the subprocess.
        # A whole URI in PGDATABASE made real pg_dump attempt a local socket.
        for key in _LIBPQ_CONNECTION_VARS:
            env.pop(key, None)
        for key in ("DATABASE_URL", "AGENT_TASK_DATABASE_URL", database_env):
            env.pop(key, None)
        env.update(connection_env)
        try:
            result = subprocess.run(
                [dump_exe, "--format=custom", "--no-owner", "--no-privileges",
                 "--file", temporary], env=env, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=1800, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise BackupError("pg_dump failed or exceeded the time limit") from None
        if result.returncode != 0:
            raise BackupError("pg_dump exited unsuccessfully; no backup was published")
        _archive_is_valid(Path(temporary), restore_bin=restore_bin)
        size = Path(temporary).stat().st_size
        digest = _sha256(Path(temporary))
        os.replace(temporary, archive)
        payload = {
            "format": "postgres-custom", "archive": archive.name,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "sha256": digest, "size_bytes": size,
            "archive_parsed": True, "restored_to_new_database": False,
            "note": "A successful pg_restore --list is not a restore rehearsal.",
        }
        _private_json(receipt, payload)
        return {"archive": str(archive), "receipt": str(receipt), "sha256": digest,
                "size_bytes": size, "archive_parsed": True,
                "restored_to_new_database": False}
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def verify_backup(receipt_path: Path, *, restore_bin: str = "pg_restore") -> dict:
    receipt_path = Path(receipt_path)
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise BackupError("Backup receipt unreadable") from None
    basename = payload.get("archive")
    if not isinstance(basename, str) or not basename.endswith(".dump") or Path(basename).name != basename:
        raise BackupError("Unsafe backup receipt archive name")
    archive = receipt_path.parent / basename
    # Never follow a receipt-controlled symlink outside the private backup folder.
    # The archive is expected to be a regular file published by os.replace().
    if archive.is_symlink() or not archive.is_file():
        raise BackupError("Unsafe backup archive type")
    if archive.stat().st_size != payload.get("size_bytes"):
        raise BackupError("Backup size mismatch")
    if _sha256(archive) != payload.get("sha256"):
        raise BackupError("Backup SHA-256 mismatch")
    _archive_is_valid(archive, restore_bin=restore_bin)
    return {"archive": str(archive), "sha256": payload["sha256"],
            "size_bytes": payload["size_bytes"], "archive_parsed": True,
            "restored_to_new_database": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Private CANO PostgreSQL backup + integrity check")
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("backup")
    make.add_argument("destination", type=Path)
    make.add_argument("--database-env", default="DATABASE_URL")
    verify = commands.add_parser("verify")
    verify.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        data = (make_backup(args.destination, database_env=args.database_env)
                if args.command == "backup" else verify_backup(args.receipt))
    except (BackupError, OSError, ValueError, KeyError):
        # Never print underlying OS or provider exceptions: some contain URLs.
        print("ERROR: PostgreSQL backup or verification failed (see local configuration)")
        return 1
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
