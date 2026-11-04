import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.task_panel import _session_database_path
from core.cano_command_center import (
    prepare_cano_team, read_cano_status, render_cano_command_center
)


class FakeStreamlit:
    def __init__(self, *, clicks=None, submit=False, task="", crossref=False):
        self.session_state = {}
        self.clicks = set(clicks or [])
        self.submit = submit
        self.task = task
        self.crossref = crossref
        self.messages = []
        self.downloaded = False
        self.metrics = {}

    def columns(self, n):
        return [self] * n

    def form(self, *a, **kw):
        return nullcontext()

    def expander(self, *a, **kw):
        return nullcontext()

    def header(self, value):
        self.messages.append(str(value))

    def subheader(self, value):
        self.messages.append(str(value))

    def metric(self, label, value):
        self.metrics[label] = value

    def caption(self, value):
        self.messages.append(str(value))

    def markdown(self, value, **kw):
        self.messages.append(str(value))

    def info(self, value):
        self.messages.append(str(value))

    def warning(self, value):
        self.messages.append(str(value))

    def error(self, value):
        self.messages.append(str(value))

    def success(self, value):
        self.messages.append(str(value))

    def button(self, label, key=None, **kw):
        lookup = key or label
        if lookup in self.clicks:
            self.clicks.remove(lookup)
            return True
        return False

    def text_area(self, label, **kw):
        return self.task

    def checkbox(self, label, **kw):
        return self.crossref

    def form_submit_button(self, label, **kw):
        result, self.submit = self.submit, False
        return result

    def link_button(self, label, url, **kw):
        self.messages.append(url)

    def selectbox(self, label, options, **kw):
        return options[0]

    def download_button(self, label, data, **kw):
        self.downloaded = True
        self.messages.append(label)

    def rerun(self):
        self.messages.append("rerun")


class FakeModel:
    def __init__(self):
        self.calls = []

    def __call__(self, prompt):
        self.calls.append(prompt)
        return "CANO aşama cevabı " + str(len(self.calls))


class CommandCenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_base = str(Path(self.tmp.name) / "colony.sqlite3")

    def test_one_click_prepares_real_roles_and_is_idempotent(self):
        colony = AgentColony(Path(self.tmp.name) / "direct.sqlite3")
        with self.assertRaises(PermissionError):
            prepare_cano_team(colony)
        prepared = prepare_cano_team(colony, approved=True)
        self.assertEqual(prepared, 7)
        again = prepare_cano_team(colony, approved=True)
        self.assertEqual(again, 7)
        roles = []
        with colony._db() as db:
            roles = [r[0] for r in db.execute("SELECT role FROM colony_agents")]
        self.assertEqual(len(roles), len(set(roles)))
        self.assertIn("research-planner", roles)
        self.assertIn("evidence-reviewer", roles)

    def test_main_cockpit_prepares_and_executes_four_stage_task(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        model = FakeModel()
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=model)
            colony = AgentColony(_session_database_path(st, self.db_base))
            self.assertEqual(read_cano_status(colony)["agents"], 7)
            st.task = "Yenilenebilir enerjinin avantajlarını araştır"
            st.submit = True
            render_cano_command_center(st, answer=model)
            self.assertEqual(len(model.calls), 4)
            self.assertIn("CANO aşama cevabı 4", " ".join(st.messages))
            self.assertTrue(st.downloaded)
            stats = read_cano_status(colony)
            self.assertEqual(stats["missions"], 1)
            self.assertEqual(stats["review_pending"], 1)
            self.assertIn("Uzman", st.metrics)

    def test_model_quota_failure_is_visible_and_task_remains_recoverable(self):
        from core.groq_team import TeamRateLimitError
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            st.task = "Sınırlı bir araştırma görevi"
            st.submit = True
            def quota_exhausted(prompt):
                raise TeamRateLimitError("safe quota limit")
            render_cano_command_center(st, answer=quota_exhausted)
            stats = read_cano_status(AgentColony(
                _session_database_path(st, self.db_base)))
            self.assertEqual(stats["blocked"], 1)
            self.assertEqual(stats["missions"], 1)
            self.assertIn("kota", " ".join(st.messages).casefold())

    def test_cockpit_exposes_truth_when_no_model(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"}, submit=True, task="Test")
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=None)
            render_cano_command_center(st, answer=None)
            colony = AgentColony(_session_database_path(st, self.db_base))
            self.assertEqual(read_cano_status(colony)["missions"], 0)
            self.assertIn("model bağlantısı", " ".join(st.messages).casefold())


if __name__ == "__main__":
    unittest.main()
