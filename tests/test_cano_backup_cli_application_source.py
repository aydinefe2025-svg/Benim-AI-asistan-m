"""CLI-level backup source identity regression tests; no database or secrets."""
import sys
import unittest
from unittest.mock import patch

from scripts import cano_encrypted_backup as backup


class BackupCLIApplicationSourceTests(unittest.TestCase):
    def run_cli(self, *args):
        argv = ["cano_encrypted_backup", "backup", "synthetic-private-dir", *args]
        with patch.object(sys, "argv", argv), patch.object(
            backup, "make_encrypted_backup", return_value={"encrypted": True}
        ) as mocked:
            with patch("builtins.print"):
                code = backup.main()
        self.assertEqual(code, 0)
        return mocked.call_args.kwargs

    def test_default_cli_backup_requires_full_application_source(self):
        """Default operator command must not silently back up an unrelated DB."""
        kwargs = self.run_cli()
        self.assertEqual(kwargs["source_profile"], "full")

    def test_explicit_partial_profile_remains_available(self):
        """Scoped operator copies remain possible when deliberately requested."""
        kwargs = self.run_cli("--require-application-profile", "tasks")
        self.assertEqual(kwargs["source_profile"], "tasks")

    def test_explicit_full_profile_remains_supported(self):
        kwargs = self.run_cli("--require-application-profile", "full")
        self.assertEqual(kwargs["source_profile"], "full")


if __name__ == "__main__":
    unittest.main()
