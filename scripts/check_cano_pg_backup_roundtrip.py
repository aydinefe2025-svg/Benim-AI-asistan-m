"""Real PostgreSQL 17/18 dump -> separate empty DB restore acceptance (synthetic CI only).

Never run against production. No customer data, API keys, paid services or
external firewall changes. The validated Docker image supplies matching pg_dump/pg_restore.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit, urlunsplit
from uuid import uuid4

import psycopg
from psycopg import sql

from scripts.cano_pg_backup import BackupError, make_backup, verify_backup


def _validate_ci_database(value: str):
    parts = urlsplit(value)
    if not (os.getenv("CANO_CI_ALLOW_DISPOSABLE_DB") == "1"
            and parts.scheme in ("postgresql", "postgres")
            and parts.hostname in ("localhost", "127.0.0.1")
            and parts.path == "/ci_persistence"
            and parts.username == "ci_user"):
        raise RuntimeError("Refusing to run outside disposable local PostgreSQL CI")
    return parts


def _for_database(parts, name: str) -> str:
    return urlunsplit((parts.scheme, parts.netloc, "/" + name, "", ""))


def _docker_cli(root: Path, tool: str, major: str) -> str:
    assert tool in {"pg_dump", "pg_restore"}
    path = root / ("docker-" + tool)
    path.write_text(
        "#!/bin/sh\nset -eu\n"
        'exec docker run --rm --network host --user 0:0 '
        '-v "$CANO_TEST_MOUNT_ROOT:$CANO_TEST_MOUNT_ROOT" '
        '-e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD '
        '-e PGDATABASE="$CANO_CI_SOURCE_DB" postgres:' + major + ' ' + tool + ' "$@"\n',
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def _restore_into_empty_database(parts, target_db: str, archive: Path, root: Path, major: str):
    env = os.environ.copy()
    env.update({
        "PGHOST": parts.hostname,
        "PGPORT": str(parts.port or 5432),
        "PGUSER": unquote(parts.username or ""),
        "PGPASSWORD": unquote(parts.password or ""),
    })
    # Only the synthetic destination database *name* enters argv.
    command = [
        "docker", "run", "--rm", "--network", "host",
        "--user", "0:0",
        "--volume", str(root) + ":" + str(root),
        "--env", "PGHOST", "--env", "PGPORT", "--env", "PGUSER",
        "--env", "PGPASSWORD",
        "postgres:" + major, "pg_restore", "--single-transaction",
        "--exit-on-error", "--no-owner", "--no-privileges",
        "--dbname", target_db, str(archive),
    ]
    result = subprocess.run(
        command, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE, check=False, timeout=180,
    )
    if result.returncode:
        # Never display stderr; some providers emit connection details.
        raise RuntimeError("Isolated synthetic PostgreSQL restore failed")


def main():
    base_url = os.environ.get("TEST_DATABASE_URL", "")
    parts = _validate_ci_database(base_url)
    major = os.environ.get("CANO_CI_PG_MAJOR", "17")
    if major not in {"17", "18"}:
        raise RuntimeError("Unsupported disposable CI PostgreSQL major")
    # Reject wrong server versions before any test database is created.
    with psycopg.connect(base_url) as db:
        server_num = int(db.execute("SHOW server_version_num").fetchone()[0])
    if server_num // 10000 != int(major):
        raise RuntimeError("Disposable CI PostgreSQL server major mismatch")
    suffix = uuid4().hex[:10]
    src_name, dst_name = "cano_ci_source_" + suffix, "cano_ci_recovered_" + suffix
    created = []
    try:
        with psycopg.connect(base_url, autocommit=True) as admin:
            for name in (src_name, dst_name):
                admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
                created.append(name)

        source = _for_database(parts, src_name)
        target = _for_database(parts, dst_name)
        expected = [
            ("owner-ci-a", {"agents": [{"id": "founder"}], "missions": []}),
            ("owner-ci-b", {"agents": [], "missions": [{"id": "m1", "state": "blocked"}]}),
        ]
        with psycopg.connect(source) as db:
            db.execute(
                "CREATE TABLE cano_ci_backup_probe ("
                "owner_key TEXT PRIMARY KEY, payload JSONB NOT NULL)"
            )
            for owner, payload in expected:
                db.execute(
                    "INSERT INTO cano_ci_backup_probe(owner_key,payload) "
                    "VALUES (%s,%s::jsonb)",
                    (owner, json.dumps(payload, sort_keys=True)),
                )

        with tempfile.TemporaryDirectory(prefix="cano-ci-backup-") as directory:
            root = Path(directory)
            env_key = "CANO_CI_DUMP_URL"
            old_root = os.environ.get("CANO_TEST_MOUNT_ROOT")
            old_url = os.environ.get(env_key)
            old_ci_connection = {key: os.environ.get(key) for key in (
                "CANO_CI_SOURCE_DB", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD")}
            try:
                os.environ["CANO_TEST_MOUNT_ROOT"] = str(root)
                os.environ[env_key] = source
                # pg_dump in Docker needs explicit libpq environment variables.
                # PGDATABASE containing a URI alone is treated as a database name
                # and otherwise falls back to an unavailable Unix socket.
                os.environ["CANO_CI_SOURCE_DB"] = src_name
                os.environ["PGHOST"] = parts.hostname or "localhost"
                os.environ["PGPORT"] = str(parts.port or 5432)
                os.environ["PGUSER"] = unquote(parts.username or "")
                os.environ["PGPASSWORD"] = unquote(parts.password or "")
                dump_bin = _docker_cli(root, "pg_dump", major)
                restore_bin = _docker_cli(root, "pg_restore", major)
                try:
                    receipt = make_backup(
                        root / "backups", database_env=env_key,
                        dump_bin=dump_bin, restore_bin=restore_bin,
                    )
                except BackupError:
                    # This probe only runs with the localhost synthetic-CI
                    # environment guard. Classify errors without revealing
                    # connection URLs, passwords or server stderr content.
                    diagnostic = subprocess.run(
                        [dump_bin, "--format=custom",
                         "--file", str(root / "diagnostic.dump")],
                        env={**os.environ, "PGDATABASE": source},
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                        timeout=120, check=False,
                    )
                    stderr = diagnostic.stderr.decode("utf-8", "replace").lower()
                    flags = {
                        "permission": "permission denied" in stderr,
                        "network": ("connection refused" in stderr
                                    or "could not connect" in stderr),
                        "version": "version mismatch" in stderr,
                        "archive_path": "could not open output file" in stderr,
                        "docker": ("docker:" in stderr
                                   or "docker daemon" in stderr),
                    }
                    print("Synthetic pg_dump failure category:",
                          diagnostic.returncode, flags)
                    # Whitelist this diagnostic to our disposable localhost
                    # CI environment; strip the entire connection URI and
                    # synthetic password before showing the error category.
                    import re
                    redacted = re.sub(
                        r"postgres(?:ql)?://[^\\s\\\"']+",
                        "<redacted-ci-db-url>", stderr,
                    )
                    redacted = redacted.replace(unquote(parts.password or ""),
                                                "<redacted>")
                    print("Synthetic pg_dump diagnostic:",
                          redacted[:650])
                    raise
                verified = verify_backup(Path(receipt["receipt"]),
                                         restore_bin=restore_bin)
                assert verified["sha256"] == receipt["sha256"]
                assert verified["restored_to_new_database"] is False
                _restore_into_empty_database(
                    parts, dst_name, Path(receipt["archive"]), root, major,
                )
                with psycopg.connect(target) as reopened:
                    rows = reopened.execute(
                        "SELECT owner_key,payload FROM cano_ci_backup_probe "
                        "ORDER BY owner_key"
                    ).fetchall()
                    assert rows == expected, "Restored rows or owner mapping differ"
                    assert reopened.execute(
                        "SELECT COUNT(*) FROM cano_ci_backup_probe "
                        "WHERE owner_key=%s", ("unrelated-owner",)
                    ).fetchone()[0] == 0, "Unexpected cross-owner record"
                # Prove verified receipts reject archive tampering after
                # successful full restore.
                archive = Path(receipt["archive"])
                with archive.open("ab") as stream:
                    stream.write(b"tamper")
                try:
                    verify_backup(Path(receipt["receipt"]), restore_bin=restore_bin)
                except BackupError:
                    pass
                else:
                    raise AssertionError("Corrupted archive passed receipt verification")
            finally:
                if old_url is None:
                    os.environ.pop(env_key, None)
                else:
                    os.environ[env_key] = old_url
                if old_root is None:
                    os.environ.pop("CANO_TEST_MOUNT_ROOT", None)
                else:
                    os.environ["CANO_TEST_MOUNT_ROOT"] = old_root
                for key, prior in old_ci_connection.items():
                    if prior is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = prior
        print("PASS: real PostgreSQL " + major + " pg_dump, parsed archive, isolated restore, "
              "two synthetic owners, exact JSONB readback, tamper detection")
    finally:
        if created:
            with psycopg.connect(base_url, autocommit=True) as admin:
                for name in reversed(created):
                    admin.execute(
                        sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                            sql.Identifier(name)
                        )
                    )


if __name__ == "__main__":
    main()
