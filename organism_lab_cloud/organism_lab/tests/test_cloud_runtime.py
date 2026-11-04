import tempfile
import unittest
from pathlib import Path

from organism_lab.cloud_runtime import default_provider, session_output_dir


class CloudRuntimeTests(unittest.TestCase):
    def test_streamlit_session_path_is_stable_but_distinct_between_sessions(self):
        with tempfile.TemporaryDirectory() as root:
            first = {}
            second = {}
            first_path = session_output_dir(root, first)
            self.assertEqual(first_path, session_output_dir(root, first))
            self.assertNotEqual(first_path, session_output_dir(root, second))
            self.assertTrue(first_path.is_dir())
            self.assertEqual(len(first["organism_lab_session_id"]), 32)

    def test_invalid_session_id_is_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            state = {"organism_lab_session_id": "../../shared"}
            path = session_output_dir(root, state)
            self.assertEqual(path.parent, Path(root).resolve())
            self.assertEqual(path.name, state["organism_lab_session_id"])
            self.assertNotIn("/", path.name)

    def test_hosted_provider_requires_a_configured_secret(self):
        self.assertEqual(default_provider(cloud_mode=True, environment={}), "offline")
        self.assertEqual(default_provider(
            cloud_mode=True, environment={"GROQ_API_KEY": "configured"}), "groq")

    def test_local_provider_remains_local(self):
        self.assertEqual(default_provider(cloud_mode=False, environment={}), "ollama")


if __name__ == "__main__":
    unittest.main()
