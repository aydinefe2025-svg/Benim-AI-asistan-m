"""Read-only, redacted owner-machine checks before CANO's Render PG18 rescue.

No SQL, firewall update, backup, migration, or credentials emitted. A passing
local preflight is never evidence of database access or disaster recovery.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
from urllib.parse import parse_qsl, unquote, urlsplit

SOURCE_ENV_NAMES = ("CANO_DATABASE_URL", "DATABASE_URL",
                    "MEMORY_DATABASE_URL", "AGENT_TASK_DATABASE_URL")
MIN_FREE_BYTES = 2 * 1024**3 + 64 * 1024**2
_PG_CLIENTS = ("pg_dump", "pg_restore", "psql")


def _configured_render_source(env: dict) -> bool:
    name = env.get("CANO_REQUIRED_RENDER_DATABASE", "").strip()
    prefix = env.get("CANO_REQUIRED_RENDER_HOST_PREFIX", "").strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_]+", name) or not re.fullmatch(r"dpg-[a-z0-9-]+", prefix):
        return False
    for key in SOURCE_ENV_NAMES:
        url = env.get(key, "").strip()
        if not url:
            continue
        try:
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            database = unquote(parsed.path.lstrip("/"))
            options = parse_qsl(parsed.query, strict_parsing=True)
            sslmodes = [value for key, value in options if key == "sslmode"]
            if (len(sslmodes) > 1 or
                    (sslmodes and sslmodes[0] not in
                     ("require", "verify-ca", "verify-full"))):
                continue
            valid_host = (host == prefix or
                          (host.startswith(prefix + ".") and host.endswith(".render.com")))
            if (parsed.scheme in ("postgres", "postgresql") and valid_host
                    and database == name and parsed.username and parsed.password
                    and parsed.port in (None, 5432)):
                return True
        except (ValueError, AttributeError):
            continue
    return False


def _pg18_clients() -> bool:
    # Do not inherit the database URI, encryption key, tokens or other credentials
    # into even the version-check subprocesses.
    allowed = ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "HOME", "LANG")
    clean_env = {name: os.environ[name] for name in allowed if name in os.environ}
    for binary in _PG_CLIENTS:
        executable = shutil.which(binary)
        if not executable:
            return False
        try:
            outcome = subprocess.run([executable, "--version"],
                                     env=clean_env, capture_output=True,
                                     text=True, timeout=4, check=False)
            if outcome.returncode or not re.search(r"\bPostgreSQL\)?\s+18(?:\.|\s|$)",
                                                   outcome.stdout or ""):
                return False
        except (OSError, subprocess.TimeoutExpired):
            return False
    return True


def _destination_checks(destination: Path) -> tuple[bool, bool]:
    try:
        destination = Path(destination).expanduser().absolute()
        parent = destination.parent
        if (destination.is_symlink() or not parent.is_dir() or parent.is_symlink()
                or (destination.exists() and (not destination.is_dir()
                                             or any(destination.iterdir())))):
            return False, False
        # On POSIX, prevent private backup outputs below group/world-accessible
        # directories. Windows ACLs need a separate operator review.
        if os.name == "posix" and stat.S_IMODE(parent.stat().st_mode) & 0o077:
            return False, False
        free_ok = shutil.disk_usage(parent).free >= MIN_FREE_BYTES
        return True, free_ok
    except (OSError, ValueError):
        return False, False


def preflight(destination: Path, *, env=None) -> dict:
    """Return only booleans and static warnings; never inspect live DB contents."""
    env = dict(os.environ if env is None else env)
    key = env.get("CANO_BACKUP_KEY_HEX", "")
    dest_ok, disk_ok = _destination_checks(destination)
    checks = {
        "owner_persistent_host": not bool(env.get("RENDER_SERVICE_ID")),
        "render_source_configured": _configured_render_source(env),
        "key_present": bool(re.fullmatch(r"[a-fA-F0-9]{64}", key)),
        "postgres18_clients": _pg18_clients(),
        "private_destination": dest_ok,
        "free_space": disk_ok,
    }
    return {
        "local_preflight_passed": all(checks.values()),
        "checks": checks,
        "windows_acl_review_required": os.name == "nt",
        "network_verified": False,
        "offsite_verified": False,
        "isolated_restore_verified": False,
        "next_owner_steps": [
            "Review private destination ACL and independently retained backup key",
            "Authorize the owner's limited /32 connection; do not open a broad allowlist",
            "Execute actual encrypted export, private offsite readback and isolated PG18 restore",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only CANO Render PG18 operator preflight")
    parser.add_argument("private_destination", type=Path)
    args = parser.parse_args()
    result = preflight(args.private_destination)
    print(json.dumps(result, indent=2))
    return 0 if result["local_preflight_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
