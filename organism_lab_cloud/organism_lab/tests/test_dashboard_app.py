"""Run via the dashboard-ui CI job with Streamlit installed."""
import unittest
from pathlib import Path
import json
import os
import tempfile
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from organism_lab.providers import trained_local_ready

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.py"

class DashboardAppTests(unittest.TestCase):

    def test_cloud_mode_fails_closed_without_persistent_auth_configuration(self):
        with patch.dict(os.environ, {
            "ORGANISM_LAB_CLOUD_MODE": "1",
            "ORGANISM_LAB_OIDC_CONFIGURED": "",
            "DATABASE_URL": "",
            "ORGANISM_LAB_OWNER_EMAIL": "",
            "ORGANISM_LAB_OWNER_KEY_SECRET": "",
        }):
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("güvenli giriş ayarları tamamlanana kadar kapalı" in item.value
                                for item in app.error))
            self.assertEqual(len(app.button), 0)

    def test_background_research_progress_is_reported_as_simulation(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}):
            output = Path(tmp) / "organism_lab_output"
            output.mkdir()
            (output / "continuous_research_status.json").write_text(json.dumps({
                "status": "running", "last_completed_cycle": 40,
            }), encoding="utf-8")
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("40 çevrim tamamlandı" in item.value and "ağırlıklarını eğitmez" in item.value
                                for item in app.caption))

    def test_simulation_button_and_metrics(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.button), 7)
        next(button for button in app.button if button.label == "Simülasyonu çalıştır").click().run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_results_survive_rerun(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        next(button for button in app.button if button.label == "Simülasyonu çalıştır").click().run()
        self.assertEqual(len(app.metric), 3)
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.metric), 3)
        self.assertEqual(len(app.get("download_button")), 1)

    def test_zero_steps(self):
        app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
        app.slider[0].set_value(0).run()
        next(button for button in app.button if button.label == "Simülasyonu çalıştır").click().run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Sıfır adım" in item.value for item in app.info))

    def test_research_campaign_does_not_call_a_model_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}), \
                patch("organism_lab.reproduction_study.summarize_with_local_model",
                      side_effect=AssertionError("UI campaign must not call a model")):
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            self.assertEqual(len(app.button), 7)
            next(button for button in app.button if button.label == "Araştırma kampanyasını çalıştır").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("Kayıt tamamlandı" in item.value for item in app.success))
            self.assertTrue(any("model kontrolü kullanılmadı" in item.value for item in app.info))
            self.assertTrue((Path(tmp) / "organism_lab_output" / "research_studies.sqlite3").exists())

    def test_bounded_discovery_report_is_saved_and_explained(self):
        report = {
            "schema": "organism-lab-bounded-discovery-sweep-v1",
            "status": "not_reproduced_on_confirmation_seeds",
            "screening": [{"mutation_rate": 0.1, "mean_difference": 0.2}],
            "selected_candidate": {"mutation_rate": 0.1, "mean_difference": 0.2},
            "confirmation": {"mutation_rate": 0.1, "mean_difference": 0.01},
            "interpretation": {"summary": "Aday ayrı tohumlarda tekrarlanmadı.",
                               "evidence_level": "exploratory_simulation_only"},
            "design": {"screening_seeds": [1, 2, 3], "confirmation_seeds": [10, 11, 12]},
        }
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}), \
                patch("organism_lab.discovery_sweep.run_discovery_sweep", return_value=report):
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            next(button for button in app.button if button.key == "run_bounded_discovery").click().run()
            self.assertFalse(app.exception)
            self.assertTrue(any("ayrı tohumlarda doğrulanmadı" in item.value for item in app.info))
            target = Path(tmp) / "organism_lab_output" / "discovery-sweep-latest.json"
            self.assertTrue(target.exists())

    def test_environment_shift_campaign_persists_without_external_model(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}):
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            next(button for button in app.button if button.label.startswith("Uyum deneyini çalıştır")).click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.dataframe), 1)
            path = Path(tmp) / "organism_lab_output" / "environment-shift-study.json"
            self.assertTrue(path.exists())
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual([row["arm"] for row in report["results"]],
                             ["mutation", "no_mutation", "no_reproduction"])
            self.assertEqual(len(report["design"]["seeds"]), 30)
            self.assertIn("no_reproduction",
                          report["paired_task_b_share_differences_mutation_minus_controls"])
            self.assertEqual(len(app.get("download_button")), 1)

    def test_literature_search_is_available_without_automatic_network_call(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}):
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            self.assertFalse(app.exception)
            self.assertTrue(any(button.key == "search_literature" for button in app.button))
            self.assertFalse((Path(tmp) / "organism_lab_output" / "research_studies.sqlite3").exists())

    def test_assistant_memory_is_user_saved_and_added_to_local_prompt(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}), \
                patch("organism_lab.providers.generate",
                      return_value={"provider": "ollama", "text": "Yanıt Türkçe olur."}) as generate:
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            if trained_local_ready():
                self.assertTrue(any("yanıt kalitesi henüz doğrulanmadı" in item.value for item in app.warning))
            else:
                self.assertTrue(any("eğitilmiş bir adaptör etkin değil" in item.value for item in app.info))
            next(item for item in app.text_input if item.key == "memory_topic").set_value("Dil tercihi")
            next(item for item in app.text_area if item.key == "memory_content").set_value("Yanıtlar Türkçe olmalı.")
            next(button for button in app.button if button.label == "Notu kalıcı hafızaya kaydet").click().run()
            self.assertTrue(any("Not kaydedildi" in item.value for item in app.success))
            next(item for item in app.text_area if item.key == "learning_query").set_value("Hangi dilde yanıt ver?")
            next(button for button in app.button if button.label == "Yerel Qwen'e sor").click().run()
            self.assertFalse(app.exception)
            self.assertIn("Yanıtlar Türkçe olmalı", generate.call_args.args[0])
            self.assertTrue(any("eklenen kayıtlı not: 1" in item.value for item in app.caption))

    def test_small_adapter_is_opt_in_until_quality_is_verified(self):
        if not trained_local_ready():
            self.skipTest("trained_local endpoint is not running")
        with tempfile.TemporaryDirectory() as tmp, \
                patch.dict(os.environ, {"ORGANISM_LAB_OUTPUT_DIR": str(Path(tmp) / "organism_lab_output")}), \
                patch("organism_lab.providers.generate",
                      return_value={"provider": "ollama", "text": "Ana model yanıtı."}) as generate:
            app = AppTest.from_file(str(DASHBOARD), default_timeout=20).run()
            choice = next(item for item in app.selectbox if item.key == "assistant_model_choice")
            self.assertEqual(choice.value, "ollama")
            self.assertTrue(any("yanıt kalitesi henüz doğrulanmadı" in item.value for item in app.warning))
            next(item for item in app.text_area if item.key == "learning_query").set_value("Test sorusu")
            next(button for button in app.button if button.label == "Yerel Qwen'e sor").click().run()
            self.assertEqual(generate.call_args.args[1], "ollama")

            app.selectbox[0].set_value("trained_local").run()
            next(item for item in app.text_area if item.key == "learning_query").set_value("Adaptörü test et")
            next(button for button in app.button if button.label == "Yerel Qwen'e sor").click().run()
            self.assertEqual(generate.call_args.args[1], "trained_local")

if __name__ == "__main__":
    unittest.main()



