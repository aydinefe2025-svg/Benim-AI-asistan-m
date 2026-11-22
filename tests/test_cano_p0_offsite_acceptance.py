"""Synthetic contract tests for the owner P0 offsite/PG18 acceptance gate.

No provider keys, private rows, production DSNs, or remote requests are used.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import cano_p0_offsite_acceptance as gate

_REAL_DOWNLOAD = gate._download_ciphertext


SOURCE = "postgresql://user:synthetic@c-7.eu-central-1.aws.neon.tech/assistant_pg"
TARGET = "postgresql://user:synthetic@localhost/cano_restore_disposable"
HOST = "c-7.eu-central-1.aws.neon.tech"
OFFSITE_HOST = "prod-files-secure.s3.us-west-2.amazonaws.com"
OFFSITE_URL = "https://" + OFFSITE_HOST + "/safe-encrypted-only?synthetic=1"
PROOF = {
    "authenticated": True,
    "receipt_authenticated": True,
    "source_preflight_metadata_authenticated": True,
    "plaintext_sha256": "a" * 64,
}
INVENTORY = {f"{s}.{t}": (7, "b" * 32) for s, t in gate.TABLES}


class OwnerP0AcceptanceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.archive = root / "original.canoenc"
        self.archive.write_bytes(b"mock-ciphertext-not-a-real-backup")
        self.receipt = root / "original.receipt.json"
        self.metadata = {
            "created_utc": "2026-11-22T13:00:00+00:00",
            "archive": self.archive.name,
            "archive_size_bytes": 100,
            "archive_sha256": "1" * 64,
            "application_source_preflight": {
                "profile": "full", "required_tables_matched": 9,
                "nonempty_table_verified": True, "source_host_pinned": True,
                "source_database_pinned": True,
            },
        }
        self.receipt.write_text(json.dumps(self.metadata))
        environ = {
            "DATABASE_URL": SOURCE,
            "CANO_RESTORE_DATABASE_URL": TARGET,
            "CANO_BACKUP_EXPECTED_HOST": HOST,
            "CANO_BACKUP_EXPECTED_DB": "assistant_pg",
            "CANO_OFFSITE_DOWNLOAD_HOST": OFFSITE_HOST,
            "CANO_OFFSITE_DOWNLOAD_URL": OFFSITE_URL,
        }
        self.environ = patch.dict(os.environ, environ, clear=True)
        self.environ.start()
        self.addCleanup(self.environ.stop)

        self.version = patch.object(gate, "_server_major", side_effect=lambda dsn: 18 if dsn == TARGET else 17)
        self.verify = patch.object(gate, "verify_encrypted_backup", return_value=PROOF.copy())
        self.inventory = patch.object(gate, "_inventory", return_value=INVENTORY.copy())
        self.download = patch.object(gate, "_download_ciphertext", return_value=100)
        self.restore = patch.object(gate, "restore_to_empty_database", return_value={
            "authenticated": True,
            "restored_to_new_database": True,
            "plaintext_sha256": "a" * 64,
        })
        self.mocks = []
        for p in (self.version, self.verify, self.inventory, self.download, self.restore):
            self.mocks.append(p.start())
            self.addCleanup(p.stop)

    def test_complete_same_ciphertext_and_full_table_parity_passes(self):
        report = gate.accept(receipt=self.receipt)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["table_count"], 19)
        self.assertEqual(report["row_count"], 133)
        self.assertTrue(report["isolated_restore"])
        self.assertFalse(report["render_pg18_source_backed_up"])
        self.assertFalse(report["live_app_environment_mapping_independently_verified"])
        self.mocks[3].assert_called_once()
        self.mocks[4].assert_called_once()
        self.assertNotIn("synthetic@", json.dumps(report))

    def test_missing_offsite_download_never_restores(self):
        del os.environ["CANO_OFFSITE_DOWNLOAD_URL"]
        with self.assertRaisesRegex(gate.AcceptanceBlocked, "offsite_download_not_configured"):
            gate.accept(receipt=self.receipt)
        self.mocks[4].assert_not_called()

    def test_unsigned_receipt_or_missing_source_preflight_refused(self):
        incomplete = PROOF.copy()
        incomplete["receipt_authenticated"] = False
        with patch.object(gate, "verify_encrypted_backup", return_value=incomplete):
            with self.assertRaisesRegex(gate.AcceptanceBlocked, "signed_current_source_proof_missing"):
                gate.accept(receipt=self.receipt)

    def test_historical_backup_before_latest_cutoff_refused(self):
        metadata = {**self.metadata, "created_utc": "2026-11-19T13:09:35+00:00"}
        self.receipt.write_text(json.dumps(metadata))
        with self.assertRaisesRegex(gate.AcceptanceBlocked, "signed_current_source_proof_missing"):
            gate.accept(receipt=self.receipt)

    def test_source_identity_and_restore_target_bounded(self):
        os.environ["DATABASE_URL"] = "postgresql://user:synthetic@render.com/assistant_pg"
        with self.assertRaisesRegex(gate.AcceptanceBlocked, "source_or_target_identity_unverified"):
            gate.accept(receipt=self.receipt)
        os.environ["DATABASE_URL"] = SOURCE
        os.environ["CANO_RESTORE_DATABASE_URL"] = "postgresql://user:synthetic@localhost/production"
        with self.assertRaisesRegex(gate.AcceptanceBlocked, "source_or_target_identity_unverified"):
            gate.accept(receipt=self.receipt)

    def test_pg17_target_refused(self):
        with patch.object(gate, "_server_major", return_value=17):
            with self.assertRaisesRegex(gate.AcceptanceBlocked, "isolated_target_not_pg18"):
                gate.accept(receipt=self.receipt)

    def test_source_record_count_below_119_refused(self):
        tiny = {k: (1, v[1]) for k, v in INVENTORY.items()}
        with patch.object(gate, "_inventory", return_value=tiny):
            with self.assertRaisesRegex(gate.AcceptanceBlocked, "source_rows_below_baseline"):
                gate.accept(receipt=self.receipt)

    def test_offsite_download_mismatch_blocks_restore(self):
        with patch.object(gate, "_download_ciphertext",
                          side_effect=gate.AcceptanceBlocked("offsite_ciphertext_mismatch")):
            with self.assertRaisesRegex(gate.AcceptanceBlocked, "offsite_ciphertext_mismatch"):
                gate.accept(receipt=self.receipt)

    def test_source_changed_or_target_content_mismatch_fails_closed(self):
        changed = {**INVENTORY, next(iter(INVENTORY)): (7, "c" * 32)}
        for inventories in ((INVENTORY, changed, INVENTORY),
                            (INVENTORY, INVENTORY, changed)):
            with self.subTest(inventories=inventories):
                with patch.object(gate, "_inventory", side_effect=inventories):
                    with self.assertRaisesRegex(gate.AcceptanceBlocked, "source_restore_parity_mismatch"):
                        gate.accept(receipt=self.receipt)

    def test_restore_failure_does_not_proclaim_success(self):
        with patch.object(gate, "restore_to_empty_database",
                          side_effect=gate.BackupError("synthetic restore error")):
            with self.assertRaises(gate.BackupError):
                gate.accept(receipt=self.receipt)

    def test_http_local_cross_host_and_notion_redirect_restriction(self):
        self.assertEqual(gate._safe_download_url(OFFSITE_URL, OFFSITE_HOST), OFFSITE_HOST)
        for raw in (
            OFFSITE_URL.replace("https://", "http://"),
            "https://127.0.0.1/backup",
            "https://example.net/backup",
            "https://different.s3.amazonaws.com/backup",
            "https://neon.tech/backup",
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(gate.AcceptanceBlocked):
                    gate._safe_download_url(raw, OFFSITE_HOST)

    def test_readback_sha_is_computed_from_actual_bytes(self):
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def geturl(self): return OFFSITE_URL
            def read(self, n): 
                if getattr(self, "_sent", False): return b""
                self._sent = True
                return b"genuine-ciphertext-fixture"

        expected = hashlib_sha(b"genuine-ciphertext-fixture")
        with tempfile.TemporaryDirectory() as root:
            with patch.object(gate, "_secure_open", return_value=Response()):
                n = _REAL_DOWNLOAD(OFFSITE_URL, OFFSITE_HOST,
                    Path(root) / "bytes.canoenc", len(b"genuine-ciphertext-fixture"), expected)
            self.assertEqual(n, len(b"genuine-ciphertext-fixture"))
            with patch.object(gate, "_secure_open", return_value=Response()):
                with self.assertRaisesRegex(gate.AcceptanceBlocked, "offsite_ciphertext_mismatch"):
                    _REAL_DOWNLOAD(OFFSITE_URL, OFFSITE_HOST,
                        Path(root) / "different.canoenc", len(b"genuine-ciphertext-fixture"), "0"*64)


def hashlib_sha(content):
    import hashlib
    return hashlib.sha256(content).hexdigest()


if __name__ == "__main__":
    unittest.main()
