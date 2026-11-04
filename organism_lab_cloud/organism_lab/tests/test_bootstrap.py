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
            self.assertEqual(path.parent, Path(root) / "organism-lab-runtime")
            self.assertNotIn("test-client-secret", environment["STREAMLIT_SECRETS_FILES"])
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

            probe_env = {**os.environ, "STREAMLIT_SECRETS_FILES": environment["STREAMLIT_SECRETS_FILES"]}
            probe = subprocess.run(
                [sys.executable, "-c",
                 "from streamlit import config; print(config.get_option('secrets.files'))"],
                capture_output=True, text=True, env=probe_env, check=False,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn(str(path), probe.stdout)

    def test_incomplete_oidc_settings_do_not_enable_login(self):
        environment = {"LAB_OIDC_CLIENT_ID": "incomplete"}
        with tempfile.TemporaryDirectory() as root:
            self.assertIsNone(write_oidc_file(environment, root))
        self.assertNotIn("ORGANISM_LAB_OIDC_CONFIGURED", environment)


if __name__ == "__main__":
    unittest.main()
