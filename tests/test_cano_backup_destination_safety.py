"""Regression tests for operator backup placement and Git secret exclusions.

These tests never connect to databases or write user backup data.
"""
from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.cano_render_rescue import main

ROOT = Path(__file__).resolve().parents[1]
RENDER_IDENTITY = {
    "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
    "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-dbkfp5bm8hqs73bba7u0-a",
}


class OperatorBackupDestinationSafetyTests(unittest.TestCase):
    def _cli(self, destination: Path):
        with patch.dict(os.environ, RENDER_IDENTITY, clear=True):
            with patch.object(sys, "argv", ["cano_render_rescue", str(destination)]):
                with patch("scripts.cano_render_rescue.backup_configured",
                           return_value={"verified_source_count": 1}) as exporter:
                    with contextlib.redirect_stdout(io.StringIO()) as output:
                        result = main()
        return result, exporter, output.getvalue()

    def test_cli_rejects_transient_os_temp_before_export(self):
        destination = Path(tempfile.gettempdir()) / "cano-unsafe-temporary-archive"
        status, exporter, output = self._cli(destination)
        self.assertEqual(status, 1)
        exporter.assert_not_called()
        self.assertNotIn(str(destination), output)

    def test_cli_rejects_archive_inside_source_checkout_before_export(self):
        destination = ROOT / "private-backups" / "accidental-archive"
        status, exporter, output = self._cli(destination)
        self.assertEqual(status, 1)
        exporter.assert_not_called()
        self.assertNotIn(str(destination), output)

    def test_cli_accepts_explicit_nonrepository_nontemp_owner_directory(self):
        destination = Path.home() / "cano-persistent-operator-backups" / "new-run"
        if ROOT == Path.home() or ROOT in destination.parents:
            self.skipTest("No independent owner directory in this test runner")
        # This test isolates destination handling; the PG18 version probe has
        # independent regression coverage in test_cano_render_pg18_preflight.
        with patch("scripts.cano_render_rescue._require_render_pg18_dump_client"):
            status, exporter, _ = self._cli(destination)
        self.assertEqual(status, 0)
        exporter.assert_called_once_with(destination)

    def test_git_refuses_to_stage_private_backup_files_by_default(self):
        for candidate in (
            "customer-data/data.canoenc",
            "customer-data/data.receipt.json",
            "customer-data/plaintext.dump",
            "customer-data/cano-rescue-manifest.json",
            "customer-data/.pgpass",
        ):
            with self.subTest(file=candidate):
                process = subprocess.run(
                    ["git", "check-ignore", "--no-index", "--quiet", "--", candidate],
                    cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=15, check=False,
                )
                self.assertEqual(
                    process.returncode, 0,
                    f"Git must ignore private recovery artifact {candidate}",
                )


if __name__ == "__main__":
    unittest.main()
