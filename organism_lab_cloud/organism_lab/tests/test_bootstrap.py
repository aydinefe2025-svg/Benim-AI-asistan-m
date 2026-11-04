import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from bootstrap import write_oidc_file


class RuntimeBootstrapTests(unittest.TestCase):
    def test_oidc_secrets_are_created_only_when_complete_and_not_in_repo(self):
        with tempfile.TemporaryDirectory() as root:
            environment = {
                "LAB_OIDC_REDIRECT_URI": "https://lab.example/oauth2callback",
                "LAB_OIDC_COOKIE_SECRET": "c" * 48,
                "LAB_OIDC_CLIENT_ID": "test-client.apps.example",
                "LAB_OIDC_CLIENT_SECRET": "test-client-secret",
                "LAB_OIDC_METADATA_URL": "https://accounts.google.com/.well-known/openid-configuration",
            }
            path = write_oidc_file(environment, root)
            self.assertTrue(path.is_file())
            self.assertEqual(environment["ORGANISM_LAB_OIDC_CONFIGURED"], "1")
            self.assertEqual(path.parent, Path(root) / "organism-lab-runtime" / ".streamlit")
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

            probe = subprocess.run(
                [sys.executable, "-c",
                 "import streamlit as st; print(bool(st.secrets.get('auth', {})))"],
                capture_output=True, text=True, env=dict(os.environ),
                cwd=path.parent.parent, check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn("True", probe.stdout)

    def test_incomplete_oidc_settings_do_not_enable_login(self):
        environment = {"LAB_OIDC_CLIENT_ID": "incomplete"}
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(write_oidc_file(environment, root))
        self.assertNotIn("ORGANISM_LAB_OIDC_CONFIGURED", environment)


if __name__ == "__main__":
    unittest.main()
