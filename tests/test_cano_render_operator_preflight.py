"""Synthetic, secret-free operator readiness checks; never connect to a database."""
import os
from pathlib import Path
import tempfile
from collections import namedtuple
import unittest
from unittest.mock import patch

from scripts.cano_render_operator_preflight import (
    _windows_acl_is_private, _windows_private_acl, preflight,
)


class OperatorPreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dest = self.root / "private" / "new-backup"
        (self.root / "private").mkdir(mode=0o700)
        self.env = {
            "CANO_REQUIRED_RENDER_DATABASE": "research_library_persistent_db",
            "CANO_REQUIRED_RENDER_HOST_PREFIX": "dpg-dbkfp5bm8hqs73bba7u0-a",
            "DATABASE_URL": "postgresql://safe:fake@dpg-dbkfp5bm8hqs73bba7u0-a.frankfurt-postgres.render.com/research_library_persistent_db?sslmode=require",
            "CANO_BACKUP_KEY_HEX": "ab" * 32,
        }

    def test_neon_only_does_not_pass_as_render_backup(self):
        e = dict(self.env, DATABASE_URL="postgresql://safe:fake@ep-someone.neon.tech/assistant_pg?sslmode=require")
        result = preflight(self.dest, env=e)
        self.assertFalse(result["local_preflight_passed"])
        self.assertFalse(result["checks"]["render_source_configured"])
        self.assertNotIn("fake", repr(result))
        self.assertNotIn("ep-someone", repr(result))

    def test_render_uri_with_disabled_tls_cannot_pass(self):
        e = dict(self.env, DATABASE_URL=self.env["DATABASE_URL"].replace(
            "sslmode=require", "sslmode=disable"))
        result = preflight(self.dest, env=e)
        self.assertFalse(result["checks"]["render_source_configured"])
        self.assertFalse(result["local_preflight_passed"])

    def test_missing_pg18_client_never_passes(self):
        with patch("shutil.which", return_value=None):
            result = preflight(self.dest, env=self.env)
        self.assertFalse(result["local_preflight_passed"])
        self.assertFalse(result["checks"]["postgres18_clients"])

    def test_pg17_tools_fail_pg18_gate(self):
        class Completed:
            returncode = 0
            stdout = "pg_dump (PostgreSQL) 17.6\n"
        with patch("shutil.which", return_value="/fake/bin/pgtool"), \
                patch("subprocess.run", return_value=Completed()):
            result = preflight(self.dest, env=self.env)
        self.assertFalse(result["local_preflight_passed"])
        self.assertFalse(result["checks"]["postgres18_clients"])

    def test_local_ready_is_not_remote_backup_or_restore(self):
        class Completed:
            returncode = 0
            stdout = "pg_dump (PostgreSQL) 18.2\n"
        with patch("shutil.which", return_value="/fake/bin/pgtool"), \
                patch("subprocess.run", return_value=Completed()), \
                patch("shutil.disk_usage", return_value=namedtuple(
                    "Usage", "total used free")(12*1024**3, 1, 8*1024**3)), \
                patch("scripts.cano_render_operator_preflight._windows_private_acl", return_value=True):
            result = preflight(self.dest, env=self.env)
        self.assertTrue(result["local_preflight_passed"], result)
        self.assertFalse(result["network_verified"])
        self.assertFalse(result["offsite_verified"])
        self.assertFalse(result["isolated_restore_verified"])
        self.assertFalse(self.dest.exists(), "preflight must be read-only")

    def test_refuses_existing_nonempty_destination_and_ephemeral_render(self):
        self.dest.mkdir()
        (self.dest / "old.canoenc").write_text("synthetic")
        with patch("shutil.which", return_value="/fake/bin/pgtool"):
            result = preflight(self.dest, env={**self.env, "RENDER_SERVICE_ID": "srv-test"})
        self.assertFalse(result["local_preflight_passed"])
        self.assertFalse(result["checks"]["owner_persistent_host"])
        self.assertFalse(result["checks"]["private_destination"])

    def test_key_is_never_exposed_in_output(self):
        result = preflight(self.dest, env={**self.env, "CANO_BACKUP_KEY_HEX": "bad-secret"})
        self.assertFalse(result["local_preflight_passed"])
        self.assertFalse(result["checks"]["key_present"])
        self.assertNotIn("bad-secret", repr(result))

    def test_windows_acl_accepts_only_owner_system_and_administrators(self):
        acl = {
            "ownerSid": "S-1-5-21-1000",
            "currentSid": "S-1-5-21-1000",
            "allowSids": ["S-1-5-21-1000", "S-1-5-18", "S-1-5-32-544"],
        }
        self.assertTrue(_windows_acl_is_private(acl))

    def test_windows_acl_rejects_broad_or_unowned_access(self):
        base = {
            "ownerSid": "S-1-5-21-1000",
            "currentSid": "S-1-5-21-1000",
            "allowSids": ["S-1-5-21-1000", "S-1-5-18"],
        }
        self.assertFalse(_windows_acl_is_private({**base, "allowSids": base["allowSids"] + ["S-1-1-0"]}))
        self.assertFalse(_windows_acl_is_private({**base, "allowSids": base["allowSids"] + ["S-1-5-32-545"]}))
        self.assertFalse(_windows_acl_is_private({**base, "ownerSid": "S-1-5-21-2000"}))
        self.assertFalse(_windows_acl_is_private({**base, "allowSids": ["S-1-5-18"]}))
        self.assertFalse(_windows_acl_is_private({"malformed": True}))

    def test_windows_acl_probe_fails_closed_without_powershell_or_valid_output(self):
        with patch("scripts.cano_render_operator_preflight.os.name", "nt"), patch("scripts.cano_render_operator_preflight.shutil.which", return_value=None):
            self.assertFalse(_windows_private_acl(self.root))
        completed = type("Completed", (), {"returncode": 0, "stdout": "not-json"})()
        with patch("scripts.cano_render_operator_preflight.os.name", "nt"), patch("scripts.cano_render_operator_preflight.shutil.which", return_value="powershell.exe"), patch("scripts.cano_render_operator_preflight.subprocess.run", return_value=completed):
            self.assertFalse(_windows_private_acl(self.root))


if __name__ == "__main__":
    unittest.main()
