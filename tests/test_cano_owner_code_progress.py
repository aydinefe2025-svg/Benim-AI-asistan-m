"""Visible, owner-only CANO code receipts instead of hidden mobile sidebar."""
import unittest
from pathlib import Path
from core.cano_development_status import (
    summarize_recent_code_jobs, render_owner_code_status,
)

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PR = "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/574"


class FakeStreamlit:
    def __init__(self):
        self.messages = []
        self.links = []

    def info(self, text):
        self.messages.append(text)

    def link_button(self, label, url):
        self.links.append((label, url))


class OwnerCodeStatusTests(unittest.TestCase):
    def test_owner_jobs_without_ci_deploy_are_unverified_and_private(self):
        st = FakeStreamlit()
        jobs = [
            {"status": "deployed", "pr_url": CANONICAL_PR,
             "goal": "private user request", "owner_key": "secret-owner"},
            {"status": "blocked", "pr_url": ""},
            {"status": "queued", "pr_url": ""},
        ]
        result = render_owner_code_status(st, jobs)
        self.assertEqual((3, 0, 1, 1, 1), (
            result["total"], result["deployed"], result["active"],
            result["blocked"], result["unverified_deployments"]))
        visible = " ".join(st.messages)
        self.assertIn("0 tam makbuzlu", visible)
        self.assertIn("1 makbuzu eksik", visible)
        self.assertIn("1 sırada/çalışıyor", visible)
        self.assertIn("1 engellendi", visible)
        self.assertNotIn("private user request", visible)
        self.assertNotIn("secret-owner", visible)
        self.assertEqual([], st.links)

    def test_untrusted_pr_url_never_becomes_external_link(self):
        st = FakeStreamlit()
        result = render_owner_code_status(st, [
            {"status": "deployed", "pr_url":
             "https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/574.evil.test"},
            {"status": "running", "pr_url": "javascript:alert(1)"},
        ])
        self.assertIsNone(result["last_pr_url"])
        self.assertEqual([], st.links)

    def test_empty_queue_is_not_reported_as_running_or_deployed(self):
        st = FakeStreamlit()
        result = render_owner_code_status(st, [])
        self.assertEqual((0, 0, 0), (
            result["deployed"], result["active"], result["blocked"]))
        self.assertIn("0 tam makbuzlu", " ".join(st.messages))

    def test_main_mobile_view_is_owner_gated_and_not_sidebar_only(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("_CODE_JOB_RECEIPTS = None", source)
        self.assertIn("_CODE_JOB_RECEIPTS = _code_store.recent()", source)
        self.assertIn(
            "if _OWNER_KEY and _CODE_JOB_RECEIPTS is not None:\n"
            "    render_owner_code_status(st, _CODE_JOB_RECEIPTS)", source)
        self.assertLess(
            source.index("render_owner_code_status(st, _CODE_JOB_RECEIPTS)"),
            source.index('st.chat_input('),
        )

    def test_model_prompt_admits_separate_queued_code_worker(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn("ayrı zamanlanmış kod işçisi", source)
        self.assertIn("güvenli PR/CI", source)


if __name__ == "__main__":
    unittest.main()
