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



def _windows_acl_is_private(payload: dict) -> bool:
    """Accept only a narrow, SID-based allowlist; never expose principal names."""
    try:
        owner = payload["ownerSid"]
        current = payload["currentSid"]
        allowed = payload["allowSids"]
        sid_pattern = re.compile(r"S-1-(?:[0-9]+-?)+")
        trusted = {"S-1-5-18", "S-1-5-32-544"}
        if (not isinstance(owner, str) or not isinstance(current, str)
                or not sid_pattern.fullmatch(owner) or not sid_pattern.fullmatch(current)
                or not isinstance(allowed, list) or not allowed):
            return False
        if any(not isinstance(sid, str) or not sid_pattern.fullmatch(sid)
               or sid not in trusted | {current} for sid in allowed):
            return False
        return owner == current and current in allowed
    except (KeyError, TypeError):
        return False


def _windows_private_acl(path: Path) -> bool:
    """Read a directory DACL via PowerShell and fail closed on any ambiguity."""
    if os.name != "nt":
        return True
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if not powershell:
        return False
    # The path is passed as an environment value, never interpolated into code.
    command = (
        "$p=$env:CANO_PREFLIGHT_ACL_PATH; "
        "$a=Get-Acl -LiteralPath $p -ErrorAction Stop; "
        "$c=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
        "$o=$a.GetOwner([Security.Principal.SecurityIdentifier]).Value; "
        "$s=@($a.Access | Where-Object {$_.AccessControlType -eq "
        "[Security.AccessControl.AccessControlType]::Allow} | "
        "ForEach-Object {$_.IdentityReference.Translate("
        "[Security.Principal.SecurityIdentifier]).Value}); "
        "@{ownerSid=$o;currentSid=$c;allowSids=$s} | ConvertTo-Json -Compress"
    )
    safe_env = {
        key: os.environ[key] for key in
        ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP")
        if key in os.environ
    }
    safe_env["CANO_PREFLIGHT_ACL_PATH"] = str(Path(path).absolute())
    try:
        outcome = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
            env=safe_env, capture_output=True, text=True, timeout=8, check=False,
        )
        if outcome.returncode:
            return False
        return _windows_acl_is_private(json.loads(outcome.stdout or ""))
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError):
        return False


def _destination_checks(destination: Path) -> tuple[bool, bool, bool]:
    try:
        destination = Path(destination).expanduser().absolute()
        parent = destination.parent
        if (destination.is_symlink() or not parent.is_dir() or parent.is_symlink()
                or (destination.exists() and (not destination.is_dir()
                                             or any(destination.iterdir())))):
            return False, False, False
        # Prevent backups below broadly accessible locations on both platforms.
        # Windows access is determined from the parent and existing destination DACLs.
        if os.name == "posix" and stat.S_IMODE(parent.stat().st_mode) & 0o077:
            return False, False, False
        acl_ok = True
        if os.name == "nt":
            acl_ok = _windows_private_acl(parent)
            if destination.exists():
                acl_ok = acl_ok and _windows_private_acl(destination)
        free_ok = shutil.disk_usage(parent).free >= MIN_FREE_BYTES
        return True, free_ok, acl_ok
    except (OSError, ValueError):
        return False, False, False


def preflight(destination: Path, *, env=None) -> dict:
    """Return only booleans and static warnings; never inspect live DB contents."""
    env = dict(os.environ if env is None else env)
    key = env.get("CANO_BACKUP_KEY_HEX", "")
    dest_ok, disk_ok, acl_ok = _destination_checks(destination)
    checks = {
        "owner_persistent_host": not bool(env.get("RENDER_SERVICE_ID")),
        "render_source_configured": _configured_render_source(env),
        "key_present": bool(re.fullmatch(r"[a-fA-F0-9]{64}", key)),
        "postgres18_clients": _pg18_clients(),
        "private_destination": dest_ok,
        "private_acl": acl_ok,
        "free_space": disk_ok,
    }
    return {
        "local_preflight_passed": all(checks.values()),
        "checks": checks,
        "windows_acl_verified": acl_ok if os.name == "nt" else None,
        "windows_acl_review_required": os.name == "nt" and not acl_ok,
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
