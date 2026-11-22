"""Owner-local, fail-closed Windows DPAPI bridge for CANO P0 encrypted recovery.

Never export an AES key, plaintext dump, or owner credentials. This tool is
**not** a cloud key recovery service and cannot work on a foreign Windows user.
It uses the existing CANO authenticated verifier and isolated restore guard.

Verify-only:
    python scripts/cano_owner_dpapi_restore.py --archive FILE.canoenc \
      --protected-key-file LOCAL_USER_KEY.dpapi --expected-sha256 HASH

Actual isolated restore requires *both* --restore-isolated and
--confirm-empty-isolated-target, plus a privately configured
CANO_RESTORE_DATABASE_URL pointing to an EMPTY cano_restore_* database.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys

try:
    from scripts.cano_encrypted_backup import (
        MAGIC, NONCE_BYTES, TAG_BYTES,
        verify_encrypted_archive_direct,
        restore_to_empty_database,
    )
except ImportError:
    from cano_encrypted_backup import (
        MAGIC, NONCE_BYTES, TAG_BYTES,
        verify_encrypted_archive_direct,
        restore_to_empty_database,
    )


class RecoveryBlocked(Exception):
    """Redacted local acceptance failure; no key or DB URL in message."""


class _DPAPIBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
    ]


def _unprotect_current_user(blob: bytes) -> bytearray:
    """Windows CurrentUser DPAPI unwrap. Nothing is emitted to logs/network."""
    if sys.platform != "win32" or not blob or len(blob) > 65536:
        raise RecoveryBlocked("Windows CurrentUser protected-key access required")
    buf = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
    wrapped = _DPAPIBlob(len(blob), buf)
    result = _DPAPIBlob()
    try:
        crypt = ctypes.WinDLL("crypt32", use_last_error=True)
        unprotect = crypt.CryptUnprotectData
        unprotect.argtypes = [
            ctypes.POINTER(_DPAPIBlob), ctypes.c_void_p, ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(_DPAPIBlob),
        ]
        unprotect.restype = wintypes.BOOL
        if not unprotect(ctypes.byref(wrapped), None, None, None, None, 0,
                         ctypes.byref(result)):
            raise RecoveryBlocked("Owner-local DPAPI key is inaccessible")
        if not 0 < result.cbData <= 4096:
            raise RecoveryBlocked("Unexpected DPAPI protected-key shape")
        return bytearray(ctypes.string_at(result.pbData, result.cbData))
    except (OSError, ValueError, ctypes.ArgumentError) as exc:
        raise RecoveryBlocked("Owner-local DPAPI key is inaccessible") from None
    finally:
        if result.pbData:
            try:
                ctypes.memset(result.pbData, 0, result.cbData)
                free = ctypes.WinDLL("kernel32", use_last_error=True).LocalFree
                free.argtypes = [ctypes.c_void_p]
                free.restype = ctypes.c_void_p
                free(ctypes.cast(result.pbData, ctypes.c_void_p))
            except (OSError, ValueError):
                pass
        ctypes.memset(ctypes.addressof(buf), 0, len(blob))


def _key_hex(plaintext: bytearray) -> str:
    """Only raw AES-256 keys or strict 64-character ASCII hex are acceptable."""
    if len(plaintext) == 32:
        return bytes(plaintext).hex()
    if len(plaintext) == 64:
        try:
            text = bytes(plaintext).decode("ascii")
        except UnicodeError:
            text = ""
        if re.fullmatch(r"[0-9a-fA-F]{64}", text):
            return text.lower()
    raise RecoveryBlocked("DPAPI file does not contain a supported AES-256 key")


@contextmanager
def _ephemeral_key_env(value: str):
    """Existing pg_restore subprocess inherits sanitized libpq-only env."""
    prior = os.environ.get("CANO_BACKUP_KEY_HEX")
    os.environ["CANO_BACKUP_KEY_HEX"] = value
    try:
        yield
    finally:
        if prior is None:
            os.environ.pop("CANO_BACKUP_KEY_HEX", None)
        else:
            os.environ["CANO_BACKUP_KEY_HEX"] = prior


def _verify_pinned_inputs(archive: Path, key_file: Path, expected_sha256: str) -> str:
    if (not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
        raise RecoveryBlocked("Expected pinned SHA-256 must be 64 lowercase hex digits")
    if archive.is_symlink() or not archive.is_file() or archive.suffix != ".canoenc":
        raise RecoveryBlocked("Encrypted archive path is invalid")
    if key_file.is_symlink() or not key_file.is_file() or key_file.suffix.lower() != ".dpapi":
        raise RecoveryBlocked("Protected key file path is invalid")
    if not 0 < key_file.stat().st_size <= 65536:
        raise RecoveryBlocked("Protected key file is invalid")
    with archive.open("rb") as f:
        head = f.read(len(MAGIC))
    if (head != MAGIC or
            archive.stat().st_size < len(MAGIC) + NONCE_BYTES + TAG_BYTES + 6):
        raise RecoveryBlocked("Encrypted archive has invalid framing")
    hash_ctx = hashlib.sha256()
    with archive.open("rb") as f:
        for chunk in iter(lambda: f.read(256 * 1024), b""):
            hash_ctx.update(chunk)
    digest = hash_ctx.hexdigest()
    if not hmac.compare_digest(digest, expected_sha256):
        raise RecoveryBlocked("Encrypted archive differs from pinned SHA-256")
    return digest


def run_local_recovery(
    archive: Path,
    key_file: Path,
    expected_sha256: str,
    *,
    restore_isolated: bool = False,
    confirm: bool = False,
    target_database_env: str = "CANO_RESTORE_DATABASE_URL",
) -> dict:
    """Authenticate the exact P0 archive; restore only into a separately gated DB."""
    archive, key_file = Path(archive), Path(key_file)
    if restore_isolated and not confirm:
        raise RecoveryBlocked("Explicit empty isolated target confirmation required")
    digest = _verify_pinned_inputs(archive, key_file, expected_sha256)
    try:
        plaintext_key = _unprotect_current_user(key_file.read_bytes())
    except Exception:
        raise RecoveryBlocked("Owner-local protected key cannot be opened") from None
    try:
        key_as_hex = _key_hex(plaintext_key)
        with _ephemeral_key_env(key_as_hex):
            try:
                proof = verify_encrypted_archive_direct(
                    archive, expected_sha256=digest)
            except Exception:
                raise RecoveryBlocked("Archive authentication failed using local key") from None
            if proof.get("authenticated") is not True:
                raise RecoveryBlocked("Archive authentication was not verified")
            result = {
                "authenticated": True,
                "ciphertext_sha256": digest,
                "plaintext_sha256": proof.get("plaintext_sha256"),
                "plaintext_size_bytes": proof.get("plaintext_size_bytes"),
                "dpapi_current_user_key_used": True,
                "receipt_authenticated": False,
                "source_identity_verified": False,
                "isolated_restore_verified": False,
            }
            if restore_isolated:
                try:
                    restored = restore_to_empty_database(
                        archive, target_db_url_env=target_database_env,
                        confirm=True)
                except Exception:
                    raise RecoveryBlocked("Isolated restore failed or target unavailable") from None
                if restored.get("restored_to_new_database") is not True:
                    raise RecoveryBlocked("Isolated restore was not confirmed")
                result["isolated_restore_verified"] = True
                result["target_database_name"] = restored.get("target_database_name")
            return result
    finally:
        for i in range(len(plaintext_key)):
            plaintext_key[i] = 0


def main() -> int:
    p = argparse.ArgumentParser(description="CANO: local CurrentUser DPAPI backup acceptance")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--protected-key-file", type=Path, required=True)
    p.add_argument("--expected-sha256", required=True)
    p.add_argument("--restore-isolated", action="store_true")
    p.add_argument("--confirm-empty-isolated-target", action="store_true")
    p.add_argument("--target-database-env", default="CANO_RESTORE_DATABASE_URL")
    opts = p.parse_args()
    try:
        result = run_local_recovery(
            opts.archive, opts.protected_key_file, opts.expected_sha256,
            restore_isolated=opts.restore_isolated,
            confirm=opts.confirm_empty_isolated_target,
            target_database_env=opts.target_database_env)
    except (RecoveryBlocked, OSError, ValueError):
        print(json.dumps({"authenticated": False, "status": "local_owner_action_or_verification_required"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
