"""Security boundary tests compatible with CANO's stdlib unittest Core CI."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "cano_render_rescue.py"
SPEC = importlib.util.spec_from_file_location("cano_render_rescue", SOURCE)
rescue = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rescue)


def source_uri(db="research_library_persistent_db", host="dpg-synthetic.frankfurt-postgres.render.com", extra=""):
    return f"postgresql://reader:secret@{host}/{db}{extra}"


class RenderRescueTests(unittest.TestCase):
    def test_rejects_temp_directory(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(rescue.RescueRefused, "temporary"):
                rescue.check_operator_environment(Path(d), repo_root=Path("/other/repo"))

    def test_rejects_render_runtime(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"RENDER": "true"}):
            with self.assertRaisesRegex(rescue.RescueRefused, "ephemeral"):
                rescue.check_operator_environment(Path(d), repo_root=Path("/other/repo"))

    def test_rejects_wrong_database_and_plaintext_remote(self):
        for url in (source_uri(db="assistant_pg"), source_uri(host="malicious.example.com"),
                    source_uri(extra="?sslmode=disable")):
            with self.subTest(url=url), self.assertRaises(rescue.RescueRefused):
                rescue.check_render_source(url)

    def test_preflight_has_no_prompt_or_connection(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(rescue, "check_operator_environment", return_value=Path(d)), \
             patch.object(rescue, "check_postgres_client", return_value="/bin/pg_dump"):
            def forbidden_prompt(_):
                self.fail("Prompted during preflight")
            result = rescue.run(Path(d), preflight=True, confirm_storage=False,
                                prompt=forbidden_prompt)
            self.assertEqual(result["preflight"], "PASS")
            self.assertFalse(result["archive_created"])

    def test_run_requires_manual_storage_confirmation(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(rescue, "check_operator_environment", return_value=Path(d)), \
             patch.object(rescue, "check_postgres_client", return_value="/bin/pg_dump"):
            def forbidden_prompt(_):
                self.fail("Prompt before explicit confirmation")
            with self.assertRaisesRegex(rescue.RescueRefused, "confirm-independent-storage"):
                rescue.run(Path(d), preflight=False, confirm_storage=False,
                           prompt=forbidden_prompt)

    def test_backup_verifies_and_leaves_no_secrets_in_environment(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(rescue, "check_operator_environment", return_value=Path(d)), \
             patch.object(rescue, "check_postgres_client", return_value="/bin/pg_dump"):
            module = ModuleType("scripts.cano_encrypted_backup")
            calls = []
            def backup(dest, **kw):
                calls.append(("backup", dest, dict(kw)))
                self.assertEqual(os.environ[rescue._DB_ENV], source_uri())
                self.assertEqual(os.environ[rescue._KEY_ENV], "a" * 64)
                return {"receipt": "/proof.receipt.json", "archive": "/proof.canoenc", "archive_sha256": "xyz"}
            def verify(receipt, **kw):
                calls.append(("verify", str(receipt), dict(kw)))
                return {"archive_sha256": "xyz"}
            module.make_encrypted_backup = backup
            module.verify_encrypted_backup = verify
            parent = ModuleType("scripts")
            values = iter((source_uri(), "a" * 64))
            with patch.dict(sys.modules, {"scripts": parent, "scripts.cano_encrypted_backup": module}), \
                 patch.dict(os.environ, {rescue._DB_ENV: "prior-url"}):
                original_key = os.environ.pop(rescue._KEY_ENV, None)
                try:
                    result = rescue.run(Path(d), preflight=False, confirm_storage=True,
                                        prompt=lambda _: next(values))
                    self.assertEqual([x[0] for x in calls], ["backup", "verify"])
                    self.assertEqual(result["cryptographic_verification"], "PASS")
                    self.assertFalse(result["independent_location_verified"])
                    self.assertFalse(result["restored_to_isolated_database"])
                    self.assertEqual(os.environ[rescue._DB_ENV], "prior-url")
                    self.assertNotIn(rescue._KEY_ENV, os.environ)
                finally:
                    if original_key is not None:
                        os.environ[rescue._KEY_ENV] = original_key

    def test_wrong_key_never_calls_backup(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(rescue, "check_operator_environment", return_value=Path(d)), \
             patch.object(rescue, "check_postgres_client", return_value="/bin/pg_dump"):
            values = iter((source_uri(), "not-a-key"))
            with self.assertRaisesRegex(rescue.RescueRefused, "256-bit"):
                rescue.run(Path(d), preflight=False, confirm_storage=True,
                           prompt=lambda _: next(values))

    def test_interactive_secret_prompt_refuses_when_terminal_is_not_private(self):
        class InsecureInput:
            def isatty(self): return False
        with patch.object(sys, "stdin", InsecureInput()):
            with self.assertRaisesRegex(rescue.RescueRefused, "interactive terminal"):
                rescue.secure_prompt("Secret: ")


if __name__ == "__main__":
    unittest.main()