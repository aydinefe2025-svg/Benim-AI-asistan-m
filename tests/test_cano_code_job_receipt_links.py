"""Authenticated owner code-job receipts: safe CI and Render links."""
import unittest
from core.cano_development_status import render_owner_code_status


class FakeUI:
    def __init__(self):
        self.messages = []
        self.links = []

    def info(self, message):
        self.messages.append(message)

    def link_button(self, label, url):
        self.links.append((label, url))


class CodeJobReceiptLinksTests(unittest.TestCase):
    def test_verified_deploy_shows_pr_ci_and_render_receipts(self):
        ui = FakeUI()
        render_owner_code_status(ui, [{
            "status": "deployed",
            "pr_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/583",
            "ci_run_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44315632105",
            "deploy_id": "dep-dbuqqtrm8hqs73b5i87g",
        }])
        urls = [link for _, link in ui.links]
        self.assertIn("https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44315632105", urls)
        self.assertIn("https://dashboard.render.com/web/srv-dbiulm8473hc73amkjtg/deploys/dep-dbuqqtrm8hqs73b5i87g", urls)

    def test_recent_valid_complete_receipt_is_not_hidden_by_newer_incomplete_row(self):
        """A stale deployed status without CI/deploy must not hide actual proof."""
        ui = FakeUI()
        render_owner_code_status(ui, [
            {"status": "deployed",
             "pr_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/610",
             "ci_run_url": "",
             "deploy_id": ""},
            {"status": "deployed",
             "pr_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/605",
             "ci_run_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44315632105",
             "deploy_id": "dep-dbuqqtrm8hqs73b5i87g"},
        ])
        urls = [url for _, url in ui.links]
        self.assertIn(
            "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44315632105",
            urls)
        self.assertIn(
            "https://dashboard.render.com/web/srv-dbiulm8473hc73amkjtg/deploys/dep-dbuqqtrm8hqs73b5i87g",
            urls)

    def test_app_has_one_phone_visible_receipt_renderer_and_no_unsafe_sidebar_pr(self):
        """Owner-only receipt links must come from the validated link renderer."""
        import ast
        from pathlib import Path
        app = Path(__file__).resolve().parents[1] / "app.py"
        source = app.read_text("utf-8")
        tree = ast.parse(source)
        calls = [node for node in ast.walk(tree)
                 if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Name)
                 and node.func.id == "render_owner_code_status"]
        self.assertEqual(len(calls), 1)
        self.assertEqual([ast.unparse(arg) for arg in calls[0].args],
                         ["st", "_CODE_JOB_RECEIPTS"])
        self.assertIn(
            "if _OWNER_KEY and _CODE_JOB_RECEIPTS is not None:", source)
        sidebar = source.split("# Authenticated owner status", 1)[1].split(
            "# 🔒 Her sağlayıcı", 1)[0]
        self.assertNotIn('st.link_button("Geliştirme PR', sidebar)
        self.assertIn("_CODE_JOB_RECEIPTS = _code_store.recent()", sidebar)

    def test_unsafe_urls_and_non_deployed_rows_never_render_receipt_links(self):
        ui = FakeUI()
        render_owner_code_status(ui, [
            {"status": "blocked", "pr_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/583",
             "ci_run_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44315632105",
             "deploy_id": "dep-dbuqqtrm8hqs73b5i87g"},
            {"status": "deployed", "pr_url": "https://github.com/evil/pull/1",
             "ci_run_url": "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/1.evil",
             "deploy_id": "dep-1/../../evil"},
        ])
        self.assertEqual([], ui.links)

    def test_private_goal_and_owner_are_not_shown(self):
        ui = FakeUI()
        render_owner_code_status(ui, [{"status": "deployed", "pr_url": "", "goal": "SECRET GOAL", "owner_key": "SECRET OWNER"}])
        self.assertNotIn("SECRET GOAL", str(ui.messages))
        self.assertNotIn("SECRET OWNER", str(ui.messages))


if __name__ == "__main__":
    unittest.main()
