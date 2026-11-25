import tempfile
import unittest
from pathlib import Path

from core.cano_source_context import build_cano_source_context


class LessonPolicySourceNotesTests(unittest.TestCase):
    def test_current_lesson_policy_has_source_provenance(self):
        root = Path(__file__).resolve().parents[1]
        result = build_cano_source_context("CANO ders benzerlik kontrolü", root)
        self.assertRegex(result, r"core/agent_colony.py:\d+.*Yaklaşık ders eşleşmesi asgari metin uzunluğu: 80")
        self.assertRegex(result, r"core/agent_colony.py:\d+.*Yaklaşık ders eşleşmesi oran eşiği: 0.9")
    def test_changed_threshold_is_extracted_from_class_method(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core/agent_colony.py").write_text(
                "class AgentColony:\n"
                "    def approve_feedback(self):\n"
                "        if min(len(signature), len(prior)) >= 123 and SequenceMatcher(None, signature, prior, autojunk=False).ratio() >= 0.95:\n"
                "            raise ValueError()\n", encoding="utf-8")
            result = build_cano_source_context("CANO ders benzerlik kontrolü", root)
            self.assertIn("Yaklaşık ders eşleşmesi asgari metin uzunluğu: 123", result)
            self.assertIn("Yaklaşık ders eşleşmesi oran eşiği: 0.95", result)
    def test_unrelated_function_does_not_supply_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "core").mkdir()
            (root / "core/agent_colony.py").write_text(
                "def unrelated():\n"
                "    return min(len(signature), len(prior)) >= 98765\n", encoding="utf-8")
            result = build_cano_source_context("CANO ders benzerlik kontrolü", root)
            self.assertNotIn("98765", result)
            self.assertNotIn("Yaklaşık ders eşleşmesi asgari metin uzunluğu:", result)
            self.assertIn("unknown", result.lower())
    def test_non_cano_lesson_question_does_not_get_repository_notes(self):
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(build_cano_source_context("ders benzerlik kontrolü", root), "")
