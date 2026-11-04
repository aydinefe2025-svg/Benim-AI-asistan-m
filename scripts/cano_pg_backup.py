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


def _libpq_env_from_url(database_url: str) -> dict[str, str]:
    """Translate a PostgreSQL URI into libpq PG* settings, without argv secrets.

    PGDATABASE is a *database name*, not a URI; putting the whole URL there
    caused a real PostgreSQL 16 connection failure in the recovery drill.
    """
    try:
        parts = urlsplit(database_url)
        if (parts.scheme not in {"postgres", "postgresql"}
                or not parts.hostname or parts.fragment or
                not parts.path.startswith("/") or len(parts.path) < 2):
            raise ValueError("Invalid PostgreSQL connection parameters")
        database_name = unquote(parts.path[1:])
        if not database_name or "\\x00" in database_name:
            raise ValueError("Invalid PostgreSQL database name")
        port = parts.port or 5432
        if port < 1 or port > 65535:
            raise ValueError("Invalid PostgreSQL port")
        option_names = {
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
            "channel_binding": "PGCHANNELBINDING",
            "connect_timeout": "PGCONNECT_TIMEOUT",
            "application_name": "PGAPPNAME",
            "target_session_attrs": "PGTARGETSESSIONATTRS",
        }
        options = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        if len(set(k for k, _ in options)) != len(options):
            raise ValueError("Duplicate PostgreSQL URI option")
        if any(key not in option_names or not val for key, val in options):
            raise ValueError("Unsupported PostgreSQL URI option")
        params = dict(options)
        local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
        sslmode = params.get("sslmode", "prefer" if local else "require")
        if not local and sslmode not in {"require", "verify-ca", "verify-full"}:
            raise ValueError("Remote PostgreSQL backup requires TLS")
        env = os.environ.copy()
        # Overwrite libpq input fields so ambient client settings cannot
        # silently connect to a different database or less-protected host.
        for key in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD",
                    "PGDATABASE", "PGSSLMODE"):
            env.pop(key, None)
        env.update({
            "PGHOST": parts.hostname,
            "PGPORT": str(port),
            "PGUSER": unquote(parts.username or ""),
            "PGPASSWORD": unquote(parts.password or ""),
            "PGDATABASE": database_name,
            "PGSSLMODE": sslmode,
        })
        for key, val in options:
            env[option_names[key]] = val
        env.setdefault("PGCONNECT_TIMEOUT", "8")
        return env
    except (ValueError, TypeError):
        # Mask malformed URI details, which may contain passwords.
        raise BackupError("Invalid PostgreSQL connection configuration") from None


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
        # Correct libpq PG* settings; URI (with credentials) must not be argv.
        env = _libpq_env_from_url(database_url)
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
