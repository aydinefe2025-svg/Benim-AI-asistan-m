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
from urllib.parse import urlsplit


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


def _run(args, *, database_url=None, runner=subprocess.run):
    environment = dict(os.environ)
    environment["PGCONNECT_TIMEOUT"] = "8"
    if database_url is not None:
        environment["PGDATABASE"] = _database_url(database_url)
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


def restore_to_isolated_test_db(destination: str | Path, *, target_url: str,
                                source_url: str, runner=subprocess.run) -> dict:
    """Explicit restore to a dedicated empty *_cano_restore_test database only."""
    source = urlsplit(_database_url(source_url))
    target = urlsplit(_database_url(target_url))
    if (target.path.rstrip("/").split("/")[-1] == source.path.rstrip("/").split("/")[-1]
            or not target.path.rstrip("/").endswith("_cano_restore_test")
            or target.hostname == "" or target_url == source_url):
        raise BackupError("Dedicated *_cano_restore_test database required")
    verify_backup(destination, runner=runner)
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
