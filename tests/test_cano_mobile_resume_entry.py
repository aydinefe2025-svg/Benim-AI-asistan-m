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
                      and "status['blocked']" in ast.unparse(n.test)
                      and "mobile_completed_id" in ast.unparse(n.test))
        new_form = next(n for n in ast.walk(function) if isinstance(n, ast.With)
                        and any("cano_cockpit_mission_form" in ast.unparse(i)
                                for i in n.items))
        self.assertLess(resume.lineno, new_form.lineno,
                        "Existing blocked mission must be directly reachable before starting a new one.")

    def test_mobile_filter_only_chooses_existing_blocked_owner_task(self):
        from core.cano_mobile_resume import select_mobile_resume_items

        target = "ae92f634-aec5-48ef-88ad-9e921b3a6e88"
        other = "00000000-0000-4000-8000-000000000001"
        items = [
            {"id": target, "status": "blocked"},
            {"id": other, "status": "blocked"},
            {"id": "00000000-0000-4000-8000-000000000002",
             "status": "review_pending"},
        ]
        self.assertEqual([items[0]], select_mobile_resume_items(items, target))
        self.assertEqual(items[:2], select_mobile_resume_items(items))
        self.assertEqual([], select_mobile_resume_items(items, "not-a-uuid"))
        self.assertEqual([], select_mobile_resume_items(items, other + "x"))
        self.assertEqual([], select_mobile_resume_items(items, [target]))
        self.assertEqual([], select_mobile_resume_items(items, "00000000-0000-4000-8000-999999999999"))

    def test_completed_task_is_selected_without_offering_resume(self):
        from core.cano_mobile_resume import select_mobile_completed_mission

        target = "ae92f634-aec5-48ef-88ad-9e921b3a6e88"
        saved = {"id": target, "status": "review_pending",
                 "stages": [{"role": role} for role in
                            ("planner", "researcher", "reviewer", "synthesis")]}
        calls = []

        def owner_get(task_id):
            calls.append(task_id)
            if task_id != target:
                raise KeyError(task_id)
            return saved

        self.assertEqual(target, select_mobile_completed_mission(owner_get, target))
        self.assertEqual([target], calls)
        self.assertIsNone(select_mobile_completed_mission(owner_get, "invalid"))
        self.assertEqual([target], calls, "Invalid links may not query owner records")
        self.assertIsNone(select_mobile_completed_mission(owner_get, "00000000-0000-4000-8000-000000000001"))
        self.assertIsNone(select_mobile_completed_mission(
            lambda _: {"id": target, "status": "blocked", "stages": saved["stages"]}, target))
        self.assertIsNone(select_mobile_completed_mission(
            lambda _: {"id": target, "status": "review_pending", "stages": []}, target))

    def test_completed_link_routes_to_saved_read_only_review(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("select_mobile_completed_mission", source)
        self.assertIn("mobile_completed_id", source)
        self.assertIn("latest_id = mobile_completed_id or", source)
        self.assertIn("and not mobile_completed_id", source)

    def test_mobile_uuid_query_is_used_to_select_only_that_mission(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn('query_params', source)
        self.assertIn('resume_mission', source)
        self.assertIn('select_mobile_resume_items', source)


if __name__ == "__main__":
    unittest.main()
