"""Exercise CANO's Organism Lab control with real Streamlit AppTest widgets."""
import unittest

from streamlit.testing.v1 import AppTest


SCRIPT = """
import streamlit as st
from core.organism_lab_panel import render_organism_lab_panel
render_organism_lab_panel(st)
"""


class CANOEmbeddedOrganismLabAppTests(unittest.TestCase):
    def test_world_button_generates_metrics_and_download(self):
        app = AppTest.from_string(SCRIPT, default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.button), 2)
        self.assertEqual(len(app.metric), 0)
        app.button[0].click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_genome_campaign_is_explicit_and_remains_after_rerun(self):
        app = AppTest.from_string(SCRIPT, default_timeout=30).run()
        self.assertFalse(app.exception)
        self.assertFalse(app.success)
        app.button[1].click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("50 dijital gözlem" in item.value for item in app.success))
        self.assertEqual(len(app.get("download_button")), 1)
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("50 dijital gözlem" in item.value for item in app.success))


if __name__ == "__main__":
    unittest.main()
