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
            self.assertIn("rerun", st.messages)
            # Simulate the Streamlit refresh that redraws metrics after submit.
            render_cano_command_center(st, answer=model)
            self.assertEqual(len(model.calls), 4)  # no duplicate provider charges
            self.assertEqual(st.metrics["Ekip görevleri"], 1)
            self.assertEqual(st.metrics["İnceleme bekleyen"], 1)
            self.assertIn("CANO aşama cevabı 4", " ".join(st.messages))
            self.assertTrue(st.downloaded)
            stats = read_cano_status(colony)
            self.assertEqual(stats["missions"], 1)
            self.assertEqual(stats["review_pending"], 1)
            self.assertIn("Uzman", st.metrics)

    def test_rate_limit_keeps_stage_checkpoint_and_shows_quota(self):
        from core.groq_team import TeamRateLimitError
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            st.task = "Sınırlı araştırma görevi"
            st.submit = True
            calls = []
            def partial_then_429(prompt):
                calls.append(prompt)
                if len(calls) == 4:
                    raise TeamRateLimitError("quota limit")
                return f"Aşama {len(calls)}"
            render_cano_command_center(st, answer=partial_then_429)
            colony = AgentColony(_session_database_path(st, self.db_base))
            status = read_cano_status(colony)
            self.assertEqual(status["blocked"], 1)
            self.assertEqual(status["missions"], 1)
            self.assertIn("kota", " ".join(st.messages).casefold())
            self.assertEqual(len(calls), 4)
            from core.collaborative_mission import CollaborativeMission
            mission = CollaborativeMission(colony).get(status["history"][0]["id"])
            self.assertEqual(len(mission["stages"]), 3)
            resumed = CollaborativeMission(colony).resume(
                mission["id"],
                client=type("Client", (), {"chat": lambda self, model, system, prompt: "Son aşama"})(),
                model="test")
            self.assertEqual(resumed["status"], "review_pending")
            self.assertEqual(len(resumed["stages"]), 4)

    def test_evidence_read_button_shows_saved_source_excerpt(self):
        from core.collaborative_mission import CollaborativeMission
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            colony = AgentColony(_session_database_path(st, self.db_base))
            mission = CollaborativeMission(colony).execute(
                "Solar study", client=type("Client", (), {
                    "chat": lambda self, model, system, prompt: "Draft"
                })(), model="test",
                source_lookup=lambda query, limit=3: [
                    {"title":"Solar study", "url":"https://doi.org/10.1234/solar"}])
            st.clicks.add("cano_read_sources_" + mission["id"])
            with patch("core.europepmc_evidence.read_publication_evidence",
                       return_value={"doi":"10.1234/solar", "title":"Solar study",
                                     "url":"https://europepmc.org/articles/PMC1234567",
                                     "status":"full_text_excerpt",
                                     "excerpt":"Measured solar output in a real study.",
                                     "claim_verified":False}) as reader:
                render_cano_command_center(st, answer=FakeModel())
                reader.assert_called_once_with("10.1234/solar")
            render_cano_command_center(st, answer=FakeModel())
            self.assertIn("Measured solar output", " ".join(st.messages))
            saved = CollaborativeMission(colony).get(mission["id"])
            self.assertEqual(saved["stages"][0]["source_documents"][0]["status"],
                             "full_text_excerpt")
            self.assertFalse(saved["stages"][0]["source_documents"][0]["claim_verified"])

    def test_cockpit_exposes_truth_when_no_model(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"}, submit=True, task="Test")
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=None)
            render_cano_command_center(st, answer=None)
            colony = AgentColony(_session_database_path(st, self.db_base))
            self.assertEqual(read_cano_status(colony)["missions"], 0)
            self.assertIn("model bağlantısı", " ".join(st.messages).casefold())


    def test_authenticated_cockpit_saves_team_and_completed_mission_to_postgres(self):
        """Provider success is not durable until owner-scoped readback succeeds."""
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        model = FakeModel()
        from core.colony_postgres import ColonySnapshotStore
        with (patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}),
              patch.object(ColonySnapshotStore, "initialize") as setup,
              patch.object(ColonySnapshotStore, "save_versioned_verified",
                           return_value=True) as save):
            render_cano_command_center(
                st, answer=model, owner_key="authenticated-owner",
                database_url="postgresql://synthetic-test")
            self.assertGreaterEqual(save.call_count, 1)
            first_owner, first_snapshot = save.call_args.args
            self.assertEqual(first_owner, "authenticated-owner")
            self.assertEqual(len(first_snapshot["agents"]), 7)
            self.assertEqual(first_snapshot["missions"], [])
            st.task = "Test solar output"
            st.submit = True
            render_cano_command_center(
                st, answer=model, owner_key="authenticated-owner",
                database_url="postgresql://synthetic-test")
            self.assertEqual(len(model.calls), 4)
            self.assertGreaterEqual(save.call_count, 2)
            final_owner, final_snapshot = save.call_args.args
            self.assertEqual(final_owner, "authenticated-owner")
            self.assertEqual(len(final_snapshot["missions"]), 1)
            self.assertEqual(final_snapshot["missions"][0]["status"], "review_pending")
            setup.assert_called()

    def test_authenticated_cockpit_persists_blocked_partial_mission(self):
        """Quota failure must not leave three produced stages only on ephemeral disk."""
        from core.colony_postgres import ColonySnapshotStore
        from core.groq_team import TeamRateLimitError
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        calls = []
        def interrupted(prompt):
            calls.append(prompt)
            if len(calls) == 4:
                raise TeamRateLimitError("429 simulated")
            return f"Draft stage {len(calls)}"
        with (patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}),
              patch.object(ColonySnapshotStore, "initialize"),
              patch.object(ColonySnapshotStore, "save_versioned_verified",
                           return_value=True) as save):
            render_cano_command_center(st, answer=interrupted, owner_key="owner",
                                       database_url="postgresql://synthetic-test")
            st.task = "One approved mission"
            st.submit = True
            render_cano_command_center(st, answer=interrupted, owner_key="owner",
                                       database_url="postgresql://synthetic-test")
            self.assertEqual(len(calls), 4)
            last = save.call_args.args[1]
            self.assertEqual(last["missions"][0]["status"], "blocked")
            self.assertEqual(len(__import__("json").loads(last["missions"][0]["stages"])), 3)

    def test_unavailable_authenticated_backup_blocks_billable_mission(self):
        """Fail before model calls when durable backing store is unavailable."""
        from core.colony_postgres import ColonySnapshotStore
        st = FakeStreamlit()
        model = FakeModel()
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            colony = AgentColony(_session_database_path(st, self.db_base))
            prepare_cano_team(colony, approved=True)
            st.task, st.submit = "Run with no durable DB", True
            with patch.object(ColonySnapshotStore, "initialize",
                              side_effect=RuntimeError("secret PostgreSQL URL password")):
                render_cano_command_center(
                    st, answer=model, owner_key="owner",
                    database_url="postgresql://synthetic-test")
        self.assertEqual(model.calls, [])
        self.assertNotIn("password", " ".join(st.messages))
        self.assertIn("PostgreSQL", " ".join(st.messages))



if __name__ == "__main__":
    unittest.main()
