"""Operator-initiated CANO Render PostgreSQL encryption rescue.

Runs on the operator's COMPUTER, not Render Free web services. Uses the existing
CANO AES-GCM streaming backup code and immediately verifies the ciphertext.
Never prints credentials, stores plaintext dumps, changes allowlists, uploads
any files, or claims a completed offsite restore. See companion runbook.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

DB_NAME = "research_library_persistent_db"
_KEY_ENV = "CANO_RESCUE_KEY_HEX"
_DB_ENV = "CANO_RESCUE_SOURCE_URL"


class RescueRefused(RuntimeError):
    """Refusal with no secrets in the message."""


def check_operator_environment(destination: Path, *, repo_root: Path | None = None) -> Path:
    if os.getenv("RENDER") or os.getenv("RENDER_SERVICE_ID") or os.getenv("RENDER_INSTANCE_ID"):
        raise RescueRefused("Do not run a backup into Render's ephemeral filesystem")
    if destination.is_symlink() or not destination.is_dir():
        raise RescueRefused("Destination must already exist as a real directory")
    resolved = destination.resolve()
    protected = [Path(tempfile.gettempdir()).resolve()]
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[1]
    protected.append(repo_root.resolve())
    if any(resolved == d or d in resolved.parents for d in protected):
        raise RescueRefused("Destination is inside a temporary directory or source repository")
    if not os.access(resolved, os.W_OK):
        raise RescueRefused("Destination is not writable")
    return resolved


def check_postgres_client() -> str:
    exe = shutil.which("pg_dump")
    if not exe:
        raise RescueRefused("Install PostgreSQL 18 or newer command-line tools: pg_dump missing")
    try:
        p = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=10, check=False)
        match = re.search(r"PostgreSQL\)?\s+(\d+)(?:\.\d+)?", p.stdout)
        if p.returncode or not match or int(match.group(1)) < 18:
            raise RescueRefused("PostgreSQL 18 or newer pg_dump is required")
    except (OSError, subprocess.TimeoutExpired):
        raise RescueRefused("Could not validate the local pg_dump version") from None
    return exe


def check_render_source(uri: str) -> None:
    try:
        p = urlsplit(uri)
        db = unquote(p.path[1:])
        host = p.hostname or ""
        if (p.scheme not in ("postgres", "postgresql")
                or db != DB_NAME
                or not host.endswith(".render.com")
                or not p.username or not p.password or p.fragment):
            raise ValueError("source")
        # Never disable TLS on a public database connection.
        if any(s in p.query.lower() for s in ("sslmode=disable", "sslmode=allow", "sslmode=prefer")):
            raise ValueError("tls")
    except ValueError:
        raise RescueRefused("Refusing an unrecognized Render source or insecure URL") from None


def secure_prompt(label: str) -> str:
    if not sys.stdin.isatty():
        raise RescueRefused("Secrets require a private interactive terminal")
    return getpass.getpass(label)


def run(destination: Path, *, preflight: bool, confirm_storage: bool,
        prompt=None, repo_root: Path | None = None) -> dict:
    dest = check_operator_environment(destination, repo_root=repo_root)
    executable = check_postgres_client()
    if preflight:
        return {"preflight": "PASS", "client": "PostgreSQL >=18",
                "source_connected": False, "archive_created": False,
                "independent_location_verified": False}
    if not confirm_storage:
        raise RescueRefused("Require --confirm-independent-storage for a backup run")
    if prompt is None:
        prompt = secure_prompt
    uri = prompt("Render EXTERNAL database URL (hidden): ")
    check_render_source(uri)
    key = prompt("Previously saved 64-character hexadecimal backup key (hidden): ")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", key or ""):
        raise RescueRefused("A separately retained 256-bit backup key is required")

    # Never pass credentials in process argv. The existing streaming backup
    # uses only libpq PG* variables for pg_dump and drops unrelated secrets.
    old = {k: os.environ.get(k) for k in (_KEY_ENV, _DB_ENV)}
    try:
        os.environ[_KEY_ENV] = key
        os.environ[_DB_ENV] = uri
        try:
            from scripts.cano_encrypted_backup import make_encrypted_backup, verify_encrypted_backup
        except ImportError:
            from cano_encrypted_backup import make_encrypted_backup, verify_encrypted_backup
        result = make_encrypted_backup(dest, database_env=_DB_ENV,
                                       key_env=_KEY_ENV, dump_bin=executable)
        verified = verify_encrypted_backup(Path(result["receipt"]), key_env=_KEY_ENV)
        if verified["archive_sha256"] != result["archive_sha256"]:
            raise RescueRefused("Encrypted backup integrity comparison failed")
        return {"encrypted_backup_created": True, "cryptographic_verification": "PASS",
                "archive": result["archive"], "receipt": result["receipt"],
                "sha256": result["archive_sha256"],
                "independent_location_verified": False, "restored_to_isolated_database": False,
                "next": "Copy archive and receipt to separately controlled offsite storage, then restore into an empty isolated database and compare records"}
    finally:
        for name, value in old.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe local CANO Render Postgres encrypted rescue")
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--confirm-independent-storage", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = run(args.destination.expanduser(), preflight=args.preflight,
                     confirm_storage=args.confirm_independent_storage)
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        # Fail closed. Cryptographic library/provider errors can include secrets;
        # do not include raw exception text in log/terminal output.
        print("REFUSED/FAILED: backup preflight or cryptographic operation did not complete; no success receipt asserted", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())