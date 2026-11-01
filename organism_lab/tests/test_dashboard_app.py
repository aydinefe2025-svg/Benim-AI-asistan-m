"""Run via the dashboard-ui CI job with Streamlit installed."""
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.py"

class DashboardAppTests(unittest.TestCase):
    def test_simulation_button_and_metrics(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.button), 1)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_zero_steps(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        app.slider[0].set_value(0).run()
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Sıfır adım" in item.value for item in app.info))

if __name__ == "__main__":
    unittest.main()
