"""Offline, synthetic authenticated-copy tests; no real account data or network."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from scripts.cano_offsite_readback import verify_offsite_copy, CopyVerificationError

KEY = bytes.fromhex("a9" * 32)
MAGIC = b"CANOENC1"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class OffsiteCopyReadbackTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="cano-offsite-test-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.source = self.root / "local"
        self.remote = self.root / "downloaded-copy"
        self.source.mkdir()
        self.key_patch = patch.dict(os.environ, {"CANO_BACKUP_KEY_HEX": KEY.hex()})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        entries = []
        for ordinal, aliases in ((1, ["CANO_DATABASE_URL", "DATABASE_URL"]),
                                  (2, ["MEMORY_DATABASE_URL", "AGENT_TASK_DATABASE_URL"])):
            folder = self.source / f"source-{ordinal:02d}"
            folder.mkdir()
            name = f"cano-pg-synthetic-{ordinal}"
            archive = folder / f"{name}.canoenc"
            receipt = folder / f"{name}.receipt.json"
            plaintext = (b"PGDMP-FAKE-TEST-DATA-" + bytes([ordinal])) * 20
            nonce = bytes([ordinal]) * 12
            header = MAGIC + nonce
            blob = header + AESGCM(KEY).encrypt(nonce, plaintext, header)
            archive.write_bytes(blob)
            receipt.write_text(json.dumps({
                "format": "cano-aes256gcm-pgdump-v1", "archive": archive.name,
                "plaintext_size_bytes": len(plaintext),
                "plaintext_sha256": sha256(plaintext),
                "archive_size_bytes": len(blob),
                "archive_sha256": sha256(blob),
                "authenticated": True,
            }), encoding="utf-8")
            entries.append({
                "source_number": ordinal,
                "env_aliases": aliases,
                "archive": f"source-{ordinal:02d}/{name}.canoenc",
                "receipt": f"source-{ordinal:02d}/{name}.receipt.json",
                "archive_sha256": sha256(blob),
                "authenticated_readback": True,
            })
        self.manifest = {
            "format": "cano-operator-encrypted-multisource-v1",
            "local_authenticated_readback": True,
            "verified_source_count": 2,
            "covered_env_names": ["CANO_DATABASE_URL", "DATABASE_URL",
                                  "MEMORY_DATABASE_URL", "AGENT_TASK_DATABASE_URL"],
            "entries": entries,
            "required_render_source_matched": True,
            "required_render_source_numbers": [1],
            "offsite_verified": False,
            "isolated_restore_verified": False,
        }
        self._write_manifest()
        self._copy()

    def _write_manifest(self):
        (self.source / "cano-rescue-manifest.json").write_text(
            json.dumps(self.manifest), encoding="utf-8")

    def _copy(self):
        if self.remote.exists():
            shutil.rmtree(self.remote)
        shutil.copytree(self.source, self.remote)

    def test_two_authenticated_copies_match_and_do_not_claim_independence_or_restore(self):
        before = {str(x.relative_to(self.remote)): sha256(x.read_bytes())
                  for x in self.remote.rglob("*") if x.is_file()}
        result = verify_offsite_copy(self.source, self.remote)
        after = {str(x.relative_to(self.remote)): sha256(x.read_bytes())
                 for x in self.remote.rglob("*") if x.is_file()}
        self.assertEqual(before, after, "Readback must not write anything")
        self.assertEqual(result["authenticated_copy_count"], 2)
        self.assertTrue(result["copied_bytes_and_authentication_verified"])
        self.assertTrue(result["required_render_source_matched"])
        self.assertFalse(result["independent_provider_verified"])
        self.assertFalse(result["isolated_restore_verified"])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_corrupt_copied_archive_is_rejected(self):
        path = next(self.remote.rglob("*.canoenc"))
        with path.open("r+b") as f:
            f.seek(-25, os.SEEK_END)
            f.write(b"X")
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_oversized_source_manifest_refuses_before_hashing(self):
        # A copied manifest is untrusted. Reject suspicious input before
        # spending CPU on hashing or allocating a large text buffer.
        manifest = self.source / "cano-rescue-manifest.json"
        with manifest.open("ab") as stream:
            stream.truncate(8 * 1024 * 1024)
        self._copy()
        with patch("scripts.cano_offsite_readback._hash_file",
                   side_effect=AssertionError("hashed an oversized manifest")):
            with self.assertRaisesRegex(CopyVerificationError,
                                        "manifest exceeds size limit"):
                verify_offsite_copy(self.source, self.remote)

    def test_oversized_downloaded_manifest_refuses_before_hashing(self):
        manifest = self.remote / "cano-rescue-manifest.json"
        with manifest.open("ab") as stream:
            stream.truncate(8 * 1024 * 1024)
        with patch("scripts.cano_offsite_readback._hash_file",
                   side_effect=AssertionError("hashed an oversized manifest")):
            with self.assertRaisesRegex(CopyVerificationError,
                                        "manifest exceeds size limit"):
                verify_offsite_copy(self.source, self.remote)

    def test_mismatched_copied_manifest_is_rejected(self):
        (self.remote / "cano-rescue-manifest.json").write_text("{}")
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_missing_receipt_is_rejected(self):
        next(self.remote.rglob("*.receipt.json")).unlink()
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_same_directory_is_rejected(self):
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.source)

    def test_hardlinked_archive_is_not_independent_copy(self):
        dst = next(self.remote.rglob("*.canoenc"))
        src = self.source / dst.relative_to(self.remote)
        dst.unlink()
        try:
            os.link(src, dst)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not allow hardlinks")
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_symlink_to_source_is_rejected(self):
        dst = next(self.remote.rglob("*.canoenc"))
        src = self.source / dst.relative_to(self.remote)
        dst.unlink()
        try:
            dst.symlink_to(src)
        except (OSError, NotImplementedError):
            self.skipTest("platform does not allow symlinks")
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_manifest_path_traversal_is_rejected(self):
        self.manifest["entries"][0]["archive"] = "../source-01/payload.canoenc"
        self._write_manifest()
        self._copy()
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_unknown_key_is_rejected(self):
        with patch.dict(os.environ, {"CANO_BACKUP_KEY_HEX": "bb" * 32}):
            with self.assertRaises(CopyVerificationError):
                verify_offsite_copy(self.source, self.remote)

    def test_manifest_not_attesting_render_remains_unproven(self):
        self.manifest["required_render_source_matched"] = False
        self.manifest["required_render_source_numbers"] = []
        self._write_manifest()
        self._copy()
        result = verify_offsite_copy(self.source, self.remote)
        self.assertFalse(result["required_render_source_matched"])
        self.assertTrue(result["copied_bytes_and_authentication_verified"])

    def test_unlisted_plaintext_dump_in_copied_bundle_is_rejected(self):
        (self.remote / "unprotected.dump").write_bytes(b"fake database rows")
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

    def test_missing_archive_is_rejected(self):
        next(self.remote.rglob("*.canoenc")).unlink()
        with self.assertRaises(CopyVerificationError):
            verify_offsite_copy(self.source, self.remote)

if __name__ == "__main__":
    unittest.main()