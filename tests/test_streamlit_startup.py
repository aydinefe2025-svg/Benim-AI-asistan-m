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

    def test_missing_both_keys_explains_configuration_and_stops(self):
        errors = self._launch_without_credentials({})
        self.assertEqual(len(errors), 1)
        self.assertIn("GROQ_API_KEY", errors[0])
        self.assertIn("GOOGLE_API_KEY", errors[0])

    def test_single_groq_key_loads_streamlit_ui_without_google_key(self):
        errors = []
        streamlit = types.ModuleType("streamlit")
        streamlit.secrets = {"GROQ_API_KEY": "private-value"}
        streamlit.set_page_config = lambda **kw: None
        streamlit.error = lambda msg: errors.append(str(msg))
        streamlit.stop = lambda: (_ for _ in ()).throw(StopRequested())
        streamlit.title = lambda *a, **kw: None
        streamlit.caption = lambda *a, **kw: None
        streamlit.markdown = lambda *a, **kw: None
        streamlit.chat_input = lambda *a, **kw: None
        streamlit.session_state = types.SimpleNamespace(messages=[])
        streamlit.sidebar = types.SimpleNamespace(
            title=lambda *a: None,
            selectbox=lambda label, options: options[0],
            success=lambda *a: None,
        )
        requests = types.ModuleType("requests")
        groq = types.ModuleType("groq")
        groq.Groq = type("Groq", (), {})
        with patch.dict(sys.modules, {"streamlit": streamlit, "requests": requests, "groq": groq}):
            runpy.run_path(str(APP), run_name="__main__")
        self.assertEqual(errors, [])
        self.assertEqual(streamlit.sidebar.selectbox("options", ("Groq",)), "Groq")

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
