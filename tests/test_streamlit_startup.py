"""Verify that the Streamlit UI reports missing secrets without crashing."""
import runpy
import sys
import types
import unittest
from unittest.mock import patch
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app.py"


class StopRequested(Exception):
    pass


class MissingSecretsTests(unittest.TestCase):
    def _launch_without_credentials(self, secrets):
        errors = []
        streamlit = types.ModuleType("streamlit")
        streamlit.secrets = secrets
        streamlit.set_page_config = lambda **kwargs: None
        streamlit.error = lambda msg: errors.append(str(msg))

        def stop():
            raise StopRequested()

        streamlit.stop = stop
        requests = types.ModuleType("requests")
        with patch.dict(sys.modules, {"streamlit": streamlit, "requests": requests}):
            with self.assertRaises(StopRequested):
                runpy.run_path(str(APP), run_name="__main__")
        return errors

    def test_missing_one_key_explains_configuration_and_stops(self):
        errors = self._launch_without_credentials({"GOOGLE_API_KEY": "do-not-leak-this-secret"})
        self.assertEqual(len(errors), 1)
        self.assertIn("GROQ_API_KEY", errors[0])
        self.assertNotIn("do-not-leak-this-secret", errors[0])

    def test_missing_secrets_file_explains_configuration_and_stops(self):
        class NoFile:
            def __getitem__(self, key):
                raise FileNotFoundError("Secrets file absent")

        errors = self._launch_without_credentials(NoFile())
        self.assertEqual(len(errors), 1)
        self.assertIn("secrets", errors[0].lower())
        self.assertNotIn("traceback", errors[0].lower())


if __name__ == "__main__":
    unittest.main()
