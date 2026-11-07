import tempfile
import unittest
from pathlib import Path

from core.cano_source_context import (
    build_cano_source_context, extract_cano_task, is_cano_code_task,
)


class CanoSourceContextTests(unittest.TestCase):
    def test_code_task_gets_only_allowlisted_files_and_secrets_are_redacted(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "core").mkdir()
            (root / "tests").mkdir()
            (root / "core/collaborative_mission.py").write_text(
                "API_KEY = 'never-send-this'\nclass Mission: pass\n", encoding="utf-8")
            (root / ".env").write_text("TOKEN=private\n", encoding="utf-8")

            context = build_cano_source_context("CANO kod mimarisini incele", root)

            self.assertIn("core/collaborative_mission.py", context)
            self.assertIn("<redacted configuration/secret assignment>", context)
            self.assertNotIn("never-send-this", context)
            self.assertNotIn("private", context)
            self.assertNotIn(".env", context)
            self.assertIn("not evidence that tests were run", context)

    def test_non_code_and_neutron_star_tasks_receive_no_context(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertFalse(is_cano_code_task("Güneş enerjisini araştır"))
            self.assertEqual(build_cano_source_context("Güneş enerjisini araştır", root), "")
            self.assertFalse(is_cano_code_task("nötron yıldızı verilerini ve kodu incele"))

    def test_extract_goal_ignores_generic_code_boundary_in_mission_prompts(self):
        code_prompt = "Make a plan. Goal: CANO GitHub kodunu incele\nExecution boundary: no code runs"
        research_prompt = "Make a plan. Goal: Güneş enerjisini araştır\nExecution boundary: no code runs"
        self.assertEqual(extract_cano_task(code_prompt), "CANO GitHub kodunu incele")
        self.assertFalse(is_cano_code_task(extract_cano_task(research_prompt)))
        self.assertEqual(extract_cano_task("No goal is present"), "")

    def test_context_selects_relevant_code_even_when_it_is_beyond_file_prefix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "core").mkdir()
            (root / "tests").mkdir()
            source = "header = True\n" * 500 + "def _run(mission_id):\n    return 'focused excerpt'\n"
            (root / "core/collaborative_mission.py").write_text(source, encoding="utf-8")
            context = build_cano_source_context("review repository code", root)
            self.assertIn("def _run(mission_id):", context)
            self.assertIn("[lines", context)

    def test_context_is_bounded_and_symlinks_cannot_escape_repository(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            (root / "core").mkdir()
            (root / "tests").mkdir()
            (root / "core/collaborative_mission.py").write_text("x" * 50000, encoding="utf-8")
            (Path(outside) / "outside.py").write_text("private", encoding="utf-8")
            try:
                (root / "core/cano_command_center.py").symlink_to(Path(outside) / "outside.py")
            except OSError:
                pass
            context = build_cano_source_context("repo kod incelemesi", root)
            self.assertLessEqual(len(context), 9000)
            self.assertNotIn("private", context)


if __name__ == "__main__":
    unittest.main()
