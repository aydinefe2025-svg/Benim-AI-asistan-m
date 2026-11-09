"""Render PG18 operator rescue client-version preflight regression tests.

Synthetic only; database subprocess never launched and no credentials required.
"""
from __future__ import annotations
import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts.cano_render_rescue import main


IDENTITY = {
    "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
    "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-dbkfp5bm8hqs73bba7u0-a",
}


class Pg18OperatorPreflightTests(unittest.TestCase):
    def _run_operator(self, version, *, available=True, rc=0):
        destination = Path.home() / "cano-pg18-preflight-synthetic-no-write"
                # Destination is unused: backup_configured is a synthetic spy.
        # The new preflight must occur before it runs.
        with patch.dict(os.environ, IDENTITY, clear=True):
            with patch.object(sys, "argv", ["cano_render_rescue", str(destination)]):
                with patch("scripts.cano_render_rescue._assert_private_destination_acl"):
                    with patch("scripts.cano_render_rescue.backup_configured",
                               return_value={"verified_source_count": 1}) as export:
                        with patch("shutil.which", return_value=(
                                "/synthetic/bin/pg_dump" if available else None)):
                            with patch("subprocess.run", return_value=SimpleNamespace(
                                    returncode=rc, stdout=version, stderr=b"")) as probe:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    status = main()
        return status, export.call_count, probe.call_count, output.getvalue()

    def test_pg17_is_refused_before_backup(self):
        status, count, calls, output = self._run_operator(
            b"pg_dump (PostgreSQL) 17.9\n")
        self.assertEqual(status, 1)
        self.assertEqual(count, 0)
        self.assertEqual(calls, 1)
        self.assertNotIn("research_library_persistent_db", output)

    def test_missing_pg_dump_is_refused_before_backup(self):
        status, count, _, output = self._run_operator(
            b"", available=False)
        self.assertEqual(status, 1)
        self.assertEqual(count, 0)
        self.assertIn("ERROR", output)

    def test_pg18_client_allows_normal_operator_flow(self):
        status, count, calls, output = self._run_operator(
            b"pg_dump (PostgreSQL) 18.2\n")
        self.assertEqual(status, 0)
        self.assertEqual(count, 1)
        self.assertEqual(calls, 1)
        self.assertIn('"verified_source_count": 1', output)

    def test_newer_pg19_is_refused_until_restore_compatibility_checked(self):
        status, count, _, output = self._run_operator(
            b"pg_dump (PostgreSQL) 19.0\n")
        self.assertEqual(status, 1)
        self.assertEqual(count, 0)
        self.assertNotIn("pg_dump (", output)

    def test_broken_or_ambiguous_client_banner_is_refused(self):
        for version in (b"pg_dump (PostgreSQL) unknown\n",
                        b"pg_dump (PostgreSQL) 18.2 -- garbage",
                        b"pg_dump (PostgreSQL) 18.2\nSECRET"):
            with self.subTest(version=version):
                status, count, _, _ = self._run_operator(version)
                self.assertEqual(status, 1)
                self.assertEqual(count, 0)

    def test_failed_version_probe_refused_before_backup(self):
        status, count, _, output = self._run_operator(
            b"pg_dump (PostgreSQL) 18.2\n", rc=1)
        self.assertEqual(status, 1)
        self.assertEqual(count, 0)
        self.assertIn("ERROR", output)


if __name__ == "__main__":
    unittest.main()
