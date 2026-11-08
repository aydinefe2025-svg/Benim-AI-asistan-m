"""Read-only verification of a copied CANO AES-GCM PostgreSQL rescue bundle.

This proves byte-for-byte copy consistency and authenticated decryption of each
copied archive. It does NOT prove the storage provider is independent, that the
full set of user databases is covered, or that any PostgreSQL restore succeeded.
No database connections, file writes, external uploads, or network access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re


class CopyVerificationError(RuntimeError):
    """Intentionally secret-free failure."""


_ALLOWED_ALIASES = frozenset({
    "CANO_DATABASE_URL", "DATABASE_URL", "MEMORY_DATABASE_URL",
    "AGENT_TASK_DATABASE_URL",
})
_MANIFEST = "cano-rescue-manifest.json"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}\Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _checked_directory(path: Path) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise CopyVerificationError("Invalid or redirected backup directory")
    return path


def _checked_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise CopyVerificationError("Invalid or redirected backup file")
    return path


def _relative_name(entry: dict, kind: str, index: int) -> Path:
    raw = entry.get(kind)
    if not isinstance(raw, str) or "\\" in raw or raw.startswith("/"):
        raise CopyVerificationError("Unsafe bundle file name")
    parts = raw.split("/")
    if (len(parts) != 2 or parts[0] != f"source-{index:02d}"
            or not _NAME.fullmatch(parts[1]) or parts[1] in (".", "..")):
        raise CopyVerificationError("Unsafe bundle file name")
    ending = ".canoenc" if kind == "archive" else ".receipt.json"
    if not parts[1].endswith(ending):
        raise CopyVerificationError("Unexpected bundle file type")
    return Path(parts[0]) / parts[1]


def _copy_matches(source: Path, copied: Path) -> str:
    _checked_file(source)
    _checked_file(copied)
    if os.path.samefile(source, copied):
        raise CopyVerificationError("Copy is the same underlying file")
    expected = _hash_file(source)
    if expected != _hash_file(copied):
        raise CopyVerificationError("Copied encrypted file digest mismatch")
    return expected


def verify_offsite_copy(source_directory: Path, copied_directory: Path) -> dict:
    """Authenticate a separately stored copy with the original bundle for comparison.

    Paths are operator-selected local/mounted directories. Never infer an
    independent cloud/provider from path names or a successful cryptographic
    readback. Explicit provider audit and isolated database restore remain P0.
    """
    source = _checked_directory(Path(source_directory))
    copied = _checked_directory(Path(copied_directory))
    src_real, dst_real = source.resolve(), copied.resolve()
    if (src_real == dst_real or src_real in dst_real.parents
            or dst_real in src_real.parents):
        raise CopyVerificationError("Source and copy directories must be separate")

    src_manifest = source / _MANIFEST
    dst_manifest = copied / _MANIFEST
    _copy_matches(src_manifest, dst_manifest)
    try:
        manifest = json.loads(src_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        raise CopyVerificationError("Invalid backup manifest") from None
    if not isinstance(manifest, dict):
        raise CopyVerificationError("Invalid backup manifest")
    entries = manifest.get("entries")
    total = manifest.get("verified_source_count")
    if (manifest.get("format") != "cano-operator-encrypted-multisource-v1"
            or manifest.get("local_authenticated_readback") is not True
            or not isinstance(entries, list) or not (1 <= len(entries) <= 4)
            or type(total) is not int or total != len(entries)):
        raise CopyVerificationError("Unverified or incomplete backup manifest")

    aliases = []
    used_files: set[str] = set()
    for ordinal, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or type(entry.get("source_number")) is not int \
                or entry["source_number"] != ordinal \
                or entry.get("authenticated_readback") is not True:
            raise CopyVerificationError("Invalid source entry")
        names = entry.get("env_aliases")
        if (not isinstance(names, list) or not names
                or any(not isinstance(a, str) or a not in _ALLOWED_ALIASES for a in names)
                or any(a in aliases for a in names) or len(set(names)) != len(names)):
            raise CopyVerificationError("Duplicate or invalid source aliases")
        aliases.extend(names)
        archive = _relative_name(entry, "archive", ordinal)
        receipt = _relative_name(entry, "receipt", ordinal)
        if (archive.name[:-len(".canoenc")]
                != receipt.name[:-len(".receipt.json")]):
            raise CopyVerificationError("Archive and receipt refer to different backups")
        if archive.as_posix() in used_files or receipt.as_posix() in used_files:
            raise CopyVerificationError("Duplicate bundle paths")
        used_files.add(archive.as_posix())
        used_files.add(receipt.as_posix())

        _checked_directory(source / archive.parent)
        _checked_directory(copied / archive.parent)
        archive_hash = _copy_matches(source / archive, copied / archive)
        _copy_matches(source / receipt, copied / receipt)
        if (not isinstance(entry.get("archive_sha256"), str)
                or archive_hash != entry["archive_sha256"]):
            raise CopyVerificationError("Source manifest checksum mismatch")
        try:
            # This authenticates the *copied* ciphertext using the operator's
            # existing offline key. No plaintext dump is written.
            from scripts.cano_encrypted_backup import verify_encrypted_backup
            proof = verify_encrypted_backup(copied / receipt)
        except Exception:
            raise CopyVerificationError("Encrypted copy authentication failed") from None
        if (proof.get("authenticated") is not True
                or proof.get("archive_sha256") != archive_hash):
            raise CopyVerificationError("Authenticated copied archive does not match")
        # Detect writes/swaps that happened while verifying.
        if (_hash_file(source / archive) != archive_hash
                or _hash_file(copied / archive) != archive_hash
                or _hash_file(source / receipt) != _hash_file(copied / receipt)):
            raise CopyVerificationError("Backup changed during readback")

    listed = manifest.get("covered_env_names")
    if (not isinstance(listed, list) or len(listed) != len(aliases)
            or any(not isinstance(x, str) for x in listed)
            or set(listed) != set(aliases)):
        raise CopyVerificationError("Incomplete source-alias coverage")
    required = manifest.get("required_render_source_numbers", [])
    if (not isinstance(required, list) or any(type(n) is not int
            or n < 1 or n > total for n in required)
            or len(required) != len(set(required))):
        raise CopyVerificationError("Invalid required source mapping")
    render_matched = manifest.get("required_render_source_matched") is True
    if bool(required) != render_matched:
        raise CopyVerificationError("Conflicting Render coverage flags")
    # Do not certify a folder containing an unexpected plaintext dump or an
    # unlisted backup file: the receipt must account for every copied file.
    expected_files = used_files | {_MANIFEST}
    expected_dirs = {f"source-{n:02d}" for n in range(1, total + 1)}
    for root in (source, copied):
        for node in root.rglob("*"):
            if node.is_symlink():
                raise CopyVerificationError("Redirected item in backup folder")
            relative = node.relative_to(root).as_posix()
            if node.is_file():
                if relative not in expected_files:
                    raise CopyVerificationError("Unexpected file in copied bundle")
            elif node.is_dir():
                if relative not in expected_dirs:
                    raise CopyVerificationError("Unexpected backup subdirectory")
            else:
                raise CopyVerificationError("Unsupported backup filesystem entry")
    if _hash_file(src_manifest) != _hash_file(dst_manifest):
        raise CopyVerificationError("Backup manifest changed during readback")
    return {
        "authenticated_copy_count": total,
        "covered_env_names": sorted(aliases),
        "copied_bytes_and_authentication_verified": True,
        "required_render_source_matched": render_matched,
        "independent_provider_verified": False,
        "isolated_restore_verified": False,
        "note": "Copy readback only; verify separate provider and isolated PostgreSQL restore independently.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CANO read-only encrypted copy verification")
    parser.add_argument("original_private_directory", type=Path)
    parser.add_argument("retrieved_copy_directory", type=Path)
    args = parser.parse_args()
    try:
        result = verify_offsite_copy(args.original_private_directory,
                                     args.retrieved_copy_directory)
    except (CopyVerificationError, OSError, TypeError, ValueError, KeyError):
        print("ERROR: encrypted backup copy could not be authenticated")
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())