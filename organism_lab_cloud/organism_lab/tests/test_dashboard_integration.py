"""Cross-check dashboard outputs against the deterministic engine."""
import json
from pathlib import Path
import unittest
from streamlit.testing.v1 import AppTest
from organism_lab.shared_world import run_shared_world

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.py"

class DashboardIntegrationTests(unittest.TestCase):
    def test_default_results_match_engine(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        next(button for button in app.button if button.label == "Simülasyonu çalıştır").click().run()
        self.assertFalse(app.exception)
        expected = run_shared_world(steps=10, energy=40, materials=12)
        self.assertEqual([str(m.value) for m in app.metric],
                         [str(expected[key]) for key in ("robots", "organisms", "successful_routes")])
        self.assertEqual(len(app.get("download_button")), 1)

    def test_custom_inputs_match_engine(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        app.slider[0].set_value(3).run()
        app.number_input[0].set_value(20).run()
        app.number_input[1].set_value(8).run()
        next(button for button in app.button if button.label == "Simülasyonu çalıştır").click().run()
        self.assertFalse(app.exception)
        expected = run_shared_world(steps=3, energy=20, materials=8)
        self.assertEqual([str(m.value) for m in app.metric],
                         [str(expected[key]) for key in ("robots", "organisms", "successful_routes")])

if __name__ == "__main__":
    unittest.main()

