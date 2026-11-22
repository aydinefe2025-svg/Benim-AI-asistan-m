"""Regression: authenticated CANO recovery should be reachable on phones."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "core" / "cano_command_center.py"


class MobileResumeEntryTests(unittest.TestCase):
    def test_existing_blocked_task_is_shown_before_new_task_form(self):
        source = PAGE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                        and n.name == "render_cano_command_center")
        resume = next(n for n in function.body if isinstance(n, ast.If)
                      and isinstance(n.test, ast.Subscript)
                      and ast.unparse(n.test) == "status['blocked']")
        )
        new_form = next(n for n in ast.walk(function) if isinstance(n, ast.With)
                        and any("cano_cockpit_mission_form" in ast.unparse(i)
                                for i in n.items))
        self.assertLess(resume.lineno, new_form.lineno,
                        "Existing blocked mission must be directly reachable before starting a new one.")

    def test_mobile_uuid_query_is_used_to_select_only_that_mission(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn('query_params', source)
        self.assertIn('resume_mission', source)
        self.assertIn('select_mobile_resume_items', source)


if __name__ == "__main__":
    unittest.main()
