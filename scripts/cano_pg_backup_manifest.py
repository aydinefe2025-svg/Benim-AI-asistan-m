"""Fail-closed, local PostgreSQL custom-format backup and isolated restore drill.

Requires PostgreSQL pg_dump and pg_restore installed in the executing environment.
No database credentials or private records are sent to GitHub/Notion/logs.
This utility is not a scheduled backup or evidence of a successful live restore.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime, timezone
from urllib.parse import parse_qsl, unquote, urlsplit


class BackupError(RuntimeError):
    pass


def _database_url(url: str | None) -> str:
    if not isinstance(url, str) or not url:
        raise BackupError("CANO_BACKUP_DATABASE_URL is required")
    parsed = urlsplit(url)
    if (parsed.scheme not in {"postgresql", "postgres"} or
            not parsed.hostname or not parsed.path.strip("/")):
        raise BackupError("PostgreSQL connection URL is invalid")
    return url


_URL_OPTIONS = {
    "sslmode": "PGSSLMODE",
    "sslrootcert": "PGSSLROOTCERT",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "channel_binding": "PGCHANNELBINDING",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
    "application_name": "PGAPPNAME",
    "options": "PGOPTIONS",
}


def _libpq_env_from_uri(uri: str, inherited: dict) -> dict:
    """Convert a standard PostgreSQL URI into secret-free argv + libpq env.

    Deliberately reject unknown query parameters rather than silently dropping
    security options. This supports the standard Render-style connection URI.
    """
    try:
        parsed = urlsplit(uri)
        if parsed.scheme not in ("postgres", "postgresql"):
            raise ValueError("scheme")
        if not parsed.hostname or not parsed.path or parsed.path == "/" or parsed.fragment:
            raise ValueError("missing host, database or unexpected fragment")
        port = parsed.port
        options = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        raise BackupError("Invalid PostgreSQL URL structure") from None
    env = inherited.copy()
    # A new destination must never receive credentials or a password file
    # inherited from a different PostgreSQL source. Only credentials carried
    # by the explicitly selected URI may enter the pg_dump/pg_restore child.
    # These app-specific URLs aren't used by libpq and should not be copied.
    for name in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR",
                 "PGUSER", "PGPASSWORD", "PGPASSFILE", "DATABASE_URL",
                 "CANO_BACKUP_DATABASE_URL", "CANO_RESTORE_TEST_DATABASE_URL"):
        env.pop(name, None)
    env["PGHOST"] = parsed.hostname
    env["PGDATABASE"] = unquote(parsed.path[1:])
    if "\x00" in env["PGDATABASE"]:
        raise BackupError("Invalid PostgreSQL database name")
    # A stale ambient PGPORT must never redirect an explicit backup URL.
    env["PGPORT"] = str(port or 5432)
    if parsed.username is not None:
        env["PGUSER"] = unquote(parsed.username)
    if parsed.password is not None:
        env["PGPASSWORD"] = unquote(parsed.password)
    seen = set()
    for key, value in options:
        if key not in _URL_OPTIONS or key in seen or not value:
            raise BackupError("Unsupported or invalid PostgreSQL URL option")
        seen.add(key)
        env[_URL_OPTIONS[key]] = value
    if not env["PGDATABASE"].strip():
        raise BackupError("PostgreSQL database name is required")
    # Never permit a remote backup to silently downgrade to plaintext.
    if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        sslmode = env.get("PGSSLMODE", "require")
        if sslmode not in {"require", "verify-ca", "verify-full"}:
            raise BackupError("Remote PostgreSQL backup requires TLS")
        env["PGSSLMODE"] = sslmode
    return env


def _run(args, *, database_url=None, runner=subprocess.run):
    environment = dict(os.environ)
    environment["PGCONNECT_TIMEOUT"] = "8"
    if database_url is not None:
        environment = _libpq_env_from_uri(_database_url(database_url), environment)
    try:
        result = runner(
            args, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, ValueError) as exc:
        raise BackupError("PostgreSQL backup utilities unavailable") from None
    if result.returncode != 0:
        raise BackupError(args[0] + " failed (exit " + str(result.returncode) + ")")
    return result


def _digest(path: Path):
    size = 0
    h = hashlib.sha256()
    with path.open("rb") as file:
        if file.read(5) != b"PGDMP":
            raise BackupError("Not a PostgreSQL custom-format archive")
        file.seek(0)
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            size += len(chunk)
            h.update(chunk)
    return size, h.hexdigest()


def _temp_file(directory: Path, *, suffix: str):
    fd, name = tempfile.mkstemp(prefix=".cano-pg-", suffix=suffix, dir=directory)
    if hasattr(os, "fchmod"):
        os.fchmod(fd, 0o600)
    else:
        os.chmod(name, 0o600)
    return fd, Path(name)


def create_backup(destination: str | Path, *, database_url: str | None = None,
                  runner=subprocess.run) -> dict:
    """Publish backup and checksum manifest without overwrite or secrets."""
    url = _database_url(database_url)
    target = Path(destination)
    manifest = target.with_name(target.name + ".manifest.json")
    if target.exists() or target.is_symlink() or manifest.exists() or manifest.is_symlink():
        raise FileExistsError("Backup or manifest already exists")
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = _temp_file(target.parent, suffix=".dump")
    os.close(fd)
    manifest_temporary = None
    published = False
    try:
        _run(["pg_dump", "--no-password", "--format=custom", "--no-owner",
              "--no-acl", "--file", str(temporary)],
             database_url=url, runner=runner)
        size, digest = _digest(temporary)
        _run(["pg_restore", "--list", str(temporary)], runner=runner)
        report = {
            "schema_version": 1, "format": "pg_custom",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "size_bytes": size, "sha256": digest,
            "status": "catalog_verified_not_restore_tested",
        }
        mf, manifest_temporary = _temp_file(target.parent, suffix=".json")
        with os.fdopen(mf, "w", encoding="utf-8") as output:
            json.dump(report, output, sort_keys=True, indent=2)
            output.flush()
            os.fsync(output.fileno())
        # Hard-link publication is exclusive and atomic: an existing file is never replaced.
        os.link(temporary, target)
        published = True
        os.link(manifest_temporary, manifest)
        return report
    except Exception:
        if published:
            target.unlink(missing_ok=True)
        raise
    finally:
        temporary.unlink(missing_ok=True)
        if manifest_temporary is not None:
            manifest_temporary.unlink(missing_ok=True)


def verify_backup(destination: str | Path, *, runner=subprocess.run) -> dict:
    target = Path(destination)
    manifest_path = target.with_name(target.name + ".manifest.json")
    report = json.loads(manifest_path.read_text(encoding="utf-8"))
    size, digest = _digest(target)
    if (report.get("schema_version") != 1 or report.get("format") != "pg_custom"
            or type(report.get("size_bytes")) is not int
            or report["size_bytes"] != size or report.get("sha256") != digest):
        raise BackupError("Backup manifest/checksum mismatch")
    _run(["pg_restore", "--list", str(target)], runner=runner)
    return {"integrity_verified": True, "size_bytes": size, "sha256": digest,
            "restore_tested": False}


# Requiring a *_cano_restore_test name is not enough: a user could point
# a restore at an already populated database bearing that suffix. Read only
# PostgreSQL's catalog before any restore that can write target rows.
_EMPTY_TARGET_CATALOG_SQL = """
SELECT
  (SELECT COUNT(*) FROM pg_catalog.pg_namespace AS n
   WHERE n.nspname NOT IN ('public', 'pg_catalog', 'information_schema')
     AND n.nspname NOT LIKE 'pg_toast%'
     AND n.nspname NOT LIKE 'pg_temp%')
  +
  (SELECT COUNT(*) FROM pg_catalog.pg_class AS c
   JOIN pg_catalog.pg_namespace AS n ON n.oid=c.relnamespace
   WHERE n.nspname='public'
     AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f'))
  +
  (SELECT COUNT(*) FROM pg_catalog.pg_proc AS p
   JOIN pg_catalog.pg_namespace AS n ON n.oid=p.pronamespace
   WHERE n.nspname='public')
  +
  (SELECT COUNT(*) FROM pg_catalog.pg_type AS t
   JOIN pg_catalog.pg_namespace AS n ON n.oid=t.typnamespace
   WHERE n.nspname='public'
     AND t.typtype IN ('c', 'd', 'e', 'r', 'm'))
"""


def _require_empty_restore_target(target_url: str, *, runner=subprocess.run) -> None:
    """Fail closed unless the selected target's catalog is independently empty.

    psql runs with the target's parsed libpq environment and no secret in
    argv.  The preflight prevents accidental population overwrites, though
    an external writer racing after this check still needs coordination.
    """
    env = _libpq_env_from_uri(_database_url(target_url), dict(os.environ))
    try:
        result = runner(
            ["psql", "--no-password", "--no-psqlrc", "--tuples-only",
             "--no-align", "--set=ON_ERROR_STOP=1", "--command",
             _EMPTY_TARGET_CATALOG_SQL],
            env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=30,
        )
    except (OSError, ValueError, subprocess.TimeoutExpired):
        raise BackupError("Restore destination must be verified empty") from None
    if (result.returncode != 0 or not isinstance(getattr(result, "stdout", None), bytes)
            or result.stdout.strip() != b"0"):
        raise BackupError("Restore destination must be verified empty")


def restore_to_isolated_test_db(destination: str | Path, *, target_url: str,
                                source_url: str, runner=subprocess.run) -> dict:
    """Explicit restore to a dedicated empty *_cano_restore_test database only."""
    source = _libpq_env_from_uri(_database_url(source_url), os.environ)
    target = _libpq_env_from_uri(_database_url(target_url), os.environ)
    if (target["PGDATABASE"] == source["PGDATABASE"]
            or not target["PGDATABASE"].endswith("_cano_restore_test")):
        raise BackupError("Dedicated *_cano_restore_test database required")
    verify_backup(destination, runner=runner)
    _require_empty_restore_target(target_url, runner=runner)
    _run(["pg_restore", "--no-password", "--single-transaction",
          "--exit-on-error", "--no-owner", "--no-acl", str(destination)],
         database_url=target_url, runner=runner)
    return {"restore_command_succeeded": True, "readback_verified": False,
            "target_kind": "isolated_test_database"}


def main():
    parser = argparse.ArgumentParser(description="Local CANO PostgreSQL disaster-recovery utility")
    parser.add_argument("mode", choices=["backup", "verify", "restore-test"])
    parser.add_argument("path")
    args = parser.parse_args()
    try:
        if args.mode == "backup":
            result = create_backup(args.path, database_url=os.environ.get("CANO_BACKUP_DATABASE_URL"))
        elif args.mode == "verify":
            result = verify_backup(args.path)
        else:
            result = restore_to_isolated_test_db(
                args.path, source_url=os.environ.get("CANO_BACKUP_DATABASE_URL", ""),
                target_url=os.environ.get("CANO_RESTORE_TEST_DATABASE_URL", ""))
    except (BackupError, FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        # Never print the exception or subprocess stderr: it can expose credentials.
        raise SystemExit("Backup/verification refused or failed; credentials not logged") from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
