"""Decrypt and verify a downloaded CANO .canoenc archive on a trusted host.

The passphrase is requested interactively and never accepted as a CLI argument,
logged, or written. The destination must not already exist. Extracted JSON files
contain private account data; choose a private folder and protect it afterward.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from core.backup_encryption import decrypt_backup
from core.cano_backup_bundle import verify_portable_bundle


def restore_to_new_directory(source: Path, destination: Path, passphrase: str) -> list[str]:
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or not source.is_file():
        raise ValueError("Encrypted backup file is unavailable")
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination must be a new directory")
    encrypted = source.read_bytes()
    bundle = decrypt_backup(encrypted, passphrase)
    files = verify_portable_bundle(bundle)
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    try:
        for name, data in files.items():
            # Keep the authenticated manifest as the durable checksum receipt.
            # The ZIP verifier has already checked every entry and checksum.
            output = destination / name
            with output.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.chmod(output, 0o600)
            except OSError:
                # Windows permissions inherit from the private destination parent.
                pass
        try:
            os.chmod(destination, 0o700)
        except OSError:
            pass
    except OSError:
        # Do not leave a partial plaintext extraction after any write failure.
        for child in destination.iterdir():
            child.unlink(missing_ok=True)
        destination.rmdir()
        raise ValueError("Backup extraction failed; partial output was removed") from None
    return sorted(files)


def main() -> int:
    parser = argparse.ArgumentParser(description="Decrypt and check a private CANO backup")
    parser.add_argument("encrypted_file", type=Path)
    parser.add_argument("new_private_directory", type=Path)
    args = parser.parse_args()
    try:
        passphrase = getpass.getpass("CANO yedek parolası: ")
        names = restore_to_new_directory(
            args.encrypted_file, args.new_private_directory, passphrase)
    except (OSError, ValueError):
        print("ERROR: CANO backup could not be authenticated or extracted.")
        return 1
    print("PASS: authenticated archive and component checksums verified.")
    print("Extracted files: " + ", ".join(names))
    print("The extracted JSON contains private data; keep the destination protected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

