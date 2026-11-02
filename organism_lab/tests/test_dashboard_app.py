"""Run via the dashboard-ui CI job with Streamlit installed."""
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.py"

class DashboardAppTests(unittest.TestCase):
    def test_simulation_button_and_metrics(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.button), 2)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_results_survive_rerun(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        app.button[0].click().run()
        self.assertEqual(len(app.metric), 3)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_zero_steps(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        app.slider[0].set_value(0).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Sıfır adım" in item.value for item in app.info))

    def test_research_campaign_persists_without_calling_a_model_in_ui_test(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch("pathlib.Path.cwd", return_value=Path(tmp)), \
                patch("organism_lab.reproduction_study.summarize_with_local_model",
                      return_value={"status": "metric_consistent", "text": "test"}):
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            self.assertEqual(len(app.button), 2)
            app.button[1].click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Kayıt tamamlandı" in item.value for item in app.success))
            self.assertTrue((Path(tmp) / "organism_lab_output" / "research_studies.sqlite3").exists())

if __name__ == "__main__":
    unittest.main()


