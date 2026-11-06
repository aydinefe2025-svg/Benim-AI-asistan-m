"""CANO-integrated lab exercises real offline engines and UI state without services."""
import hashlib
import json
import unittest
from contextlib import nullcontext
from unittest.mock import patch

from core.organism_lab_panel import (
    explain_campaign, json_export, render_organism_lab_panel, run_checked_campaign
)
from organism_lab.shared_world import run_shared_world


class FakeStreamlit:
    def __init__(self, pressed=()):
        self.sidebar = self
        self.pressed = set(pressed)
        self.session_state = {}
        self.downloads = []
        self.metrics = []
        self.errors = []
        self.successes = []
        self.warnings = []
        self.markdown_blocks = []

    def expander(self, *_args, **_kwargs):
        return nullcontext()

    def caption(self, *_args, **_kwargs):
        pass

    def markdown(self, text, **_kwargs):
        self.markdown_blocks.append(text)

    def slider(self, *_args, **_kwargs):
        return 10

    def number_input(self, label, **_kwargs):
        return 40 if "enerji" in label.lower() else 12

    def button(self, _text, *, key, **_kwargs):
        return key in self.pressed

    def metric(self, label, value):
        self.metrics.append((label, value))

    def download_button(self, _label, **kwargs):
        self.downloads.append(kwargs)

    def dataframe(self, *_args, **_kwargs):
        pass

    def divider(self):
        pass

    def error(self, message):
        self.errors.append(message)

    def success(self, message):
        self.successes.append(message)

    def warning(self, message):
        self.warnings.append(message)


class OrganismPanelTests(unittest.TestCase):
    def test_bounded_campaign_is_reproducible_and_downloadable(self):
        with patch("organism_lab.providers.generate",
                   side_effect=AssertionError("Must not call an LLM")):
            a = run_checked_campaign(seeds=3, steps=10)
            b = run_checked_campaign(seeds=3, steps=10)
        self.assertEqual(a["json"], b["json"])
        self.assertEqual(a["sha256"], hashlib.sha256(a["json"]).hexdigest())
        self.assertEqual(a["observations"], 15)
        self.assertEqual(json.loads(a["json"])["design"]["steps"], 10)

    def test_out_of_budget_campaign_is_rejected(self):
        for seed_count, steps in ((1, 20), (11, 20), (3, 0),
                                  (3, 101), (True, 20), (3, 1.5)):
            with self.subTest(seed_count=seed_count, steps=steps):
                with self.assertRaises(ValueError):
                    run_checked_campaign(seeds=seed_count, steps=steps)

    def test_campaign_explanation_uses_computed_metrics_and_limits_claims(self):
        report = run_checked_campaign(seeds=3, steps=10)["report"]
        explanation = explain_campaign(report)
        self.assertIn("3 aynı başlangıç tohumu", explanation)
        self.assertIn("En büyük ortalama fark", explanation)
        self.assertIn("yalnızca dijital model", explanation)
        self.assertIn("gerçek hücre", explanation)
        with self.assertRaises(ValueError):
            explain_campaign({"design": {}, "results": [], "observations": []})

    def test_main_app_panel_performs_real_simulation_and_offers_exports(self):
        ui = FakeStreamlit(pressed=("cano_organism_world_run",
                                    "cano_organism_campaign_run"))
        render_organism_lab_panel(ui)
        expected = run_shared_world(steps=10, energy=40, materials=12)
        self.assertEqual(ui.session_state["cano_organism_world_result"], expected)
        self.assertEqual(len(ui.downloads), 2)
        self.assertEqual(len(ui.metrics), 3)
        self.assertEqual(ui.session_state["cano_organism_campaign_result"]["observations"], 50)
        self.assertEqual(len(ui.markdown_blocks), 1)
        self.assertIn("Ne bulundu?", ui.markdown_blocks[0])
        self.assertTrue(all("json" in item["mime"] for item in ui.downloads))
        self.assertTrue(any("PostgreSQL" in m for m in ui.warnings))
        self.assertEqual(ui.errors, [])
        ui.pressed.clear()
        render_organism_lab_panel(ui)
        self.assertEqual(len(ui.downloads), 4)
        self.assertEqual(len(ui.successes), 2)

    def test_replay_mismatch_cannot_report_success(self):
        ui = FakeStreamlit(pressed=("cano_organism_campaign_run",))
        with patch("core.organism_lab_panel.run_study",
                   side_effect=[{"results": [1]}, {"results": [2]}]):
            render_organism_lab_panel(ui)
        self.assertTrue(ui.errors)
        self.assertFalse(ui.successes)
        self.assertNotIn("cano_organism_campaign_result", ui.session_state)

    def test_app_calls_panel_after_authentication_gate(self):
        from pathlib import Path
        app = (Path(__file__).resolve().parents[1] / "app.py").read_text("utf-8")
        self.assertIn("from core.organism_lab_panel import render_organism_lab_panel", app)
        self.assertIn("render_organism_lab_panel(st)", app)
        self.assertLess(app.index("render_auth_gate(st"), app.index("render_organism_lab_panel(st)"))


if __name__ == "__main__":
    unittest.main()
