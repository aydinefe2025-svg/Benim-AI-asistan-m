"""Prevent a fresh authenticated session from replacing a nonempty owner backup."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.cano_command_center import render_cano_command_center
from core.task_panel import _session_database_path
from tests.test_cano_command_center import FakeModel, FakeStreamlit


class AuthenticatedBackupGuardTests(unittest.TestCase):
    def test_authenticated_cockpit_offers_full_encrypted_export_not_plain_json(self):
        class EmptyQueue:
            def list(self):
                return []

            def events(self, _job_id):
                return []

        with tempfile.TemporaryDirectory() as temp:
            base = str(Path(temp) / "colony.sqlite3")
            st = FakeStreamlit(clicks={"cano_prepare_team"})
            with (patch.dict("os.environ", {
                    "AGENT_COLONY_DB_PATH": base, "APP_AUTH_REQUIRED": "true"}),
                  patch("core.cano_command_center.ColonySnapshotStore") as Store):
                Store.return_value.load.return_value = None
                Store.return_value.save_versioned_verified.return_value = True
                render_cano_command_center(
                    st, answer=FakeModel(), owner_key="owner-123",
                    database_url="postgresql://synthetic-test", memories=[],
                    research_tasks=b'{"schema":"research-task-export-v1","tasks":[]}',
                    authorized_queue_store=EmptyQueue())
                joined = " ".join(st.messages)
                self.assertIn("şifreli dış yedek", joined)
                self.assertNotIn("CANO ajanlarını, görevlerini ve dersleri JSON yedekle", joined)
                self.assertFalse(st.downloaded)

    def test_fresh_authenticated_session_restores_owner_backup_before_team_setup(self):
        with tempfile.TemporaryDirectory() as temp:
            base = str(Path(temp) / "colony.sqlite3")
            st = FakeStreamlit(clicks={"cano_prepare_team"})
            model = FakeModel()
            saved = {"agents": [{
                "id": "existing-founder", "parent_id": None,
                "generation": 0, "role": "research",
                "instructions": "Research", "state": "active",
                "created_at": "2026-11-04"}],
                "feedback": [], "reviews": [], "missions": []}
            with (patch.dict("os.environ", {
                    "AGENT_COLONY_DB_PATH": base, "APP_AUTH_REQUIRED": "true"}),
                  patch("core.cano_command_center.ColonySnapshotStore") as Store):
                Store.return_value.load.return_value = saved
                render_cano_command_center(
                    st, answer=model, owner_key="owner-123",
                    database_url="postgresql://synthetic-test")
                Store.return_value.load.assert_called_with("owner-123")
                Store.return_value.save_versioned_verified.assert_not_called()
                self.assertIn("geri yüklendi", " ".join(st.messages).lower())
                local = AgentColony(_session_database_path(st, base))
                with local._db() as db:
                    self.assertEqual(db.execute(
                        "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 1)
                self.assertEqual(st.session_state["_cano_backup_expected"], saved)
            self.assertEqual(model.calls, [])

    def test_fresh_session_fails_closed_if_existing_backup_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as temp:
            base = str(Path(temp) / "colony.sqlite3")
            st = FakeStreamlit(clicks={"cano_prepare_team"})
            with (patch.dict("os.environ", {
                    "AGENT_COLONY_DB_PATH": base, "APP_AUTH_REQUIRED": "true"}),
                  patch("core.cano_command_center.ColonySnapshotStore") as Store):
                Store.return_value.load.side_effect = OSError("private connection info")
                render_cano_command_center(
                    st, answer=FakeModel(), owner_key="owner-123",
                    database_url="postgresql://synthetic-test")
                Store.return_value.save_versioned_verified.assert_not_called()
                self.assertNotIn("private connection info", " ".join(st.messages))
                local = AgentColony(_session_database_path(st, base))
                with local._db() as db:
                    self.assertEqual(db.execute(
                        "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 0)


    def test_cockpit_preflight_supplies_exact_remote_baseline_for_stale_tab_rejection(self):
        """No billable model requests when owner-scoped snapshot CAS refuses the tab."""
        from core.cano_command_center import prepare_cano_team, _snapshot
        with tempfile.TemporaryDirectory() as temp:
            base = str(Path(temp) / "colony.sqlite3")
            st = FakeStreamlit()
            colony = AgentColony(_session_database_path(st, base))
            prepare_cano_team(colony, approved=True)
            baseline = _snapshot(colony)
            model = FakeModel()
            with (patch.dict("os.environ", {
                    "AGENT_COLONY_DB_PATH": base, "APP_AUTH_REQUIRED": "true"}),
                  patch("core.cano_command_center.ColonySnapshotStore") as Store):
                Store.return_value.load.return_value = baseline
                render_cano_command_center(
                    st, answer=model, owner_key="owner-123",
                    database_url="postgresql://synthetic-test")
                st.task = "Run only if current snapshot matches"
                st.submit = True
                Store.return_value.save_versioned_verified.side_effect = RuntimeError(
                    "newer tab already committed")
                render_cano_command_center(
                    st, answer=model, owner_key="owner-123",
                    database_url="postgresql://synthetic-test")
                Store.return_value.save_versioned_verified.assert_called()
                self.assertEqual(
                    Store.return_value.save_versioned_verified.call_args.kwargs["expected_prior"],
                    baseline)
            self.assertEqual(model.calls, [])


    def test_restarted_running_mission_is_allowed_as_blocked_after_owner_restore(self):
        """Restoring an interrupted mission safely marks it blocked, not a stale conflict."""
        from core.cano_command_center import prepare_cano_team, _snapshot
        from core.collaborative_mission import CollaborativeMission
        with tempfile.TemporaryDirectory() as temp:
            base = str(Path(temp) / "colony.sqlite3")
            st = FakeStreamlit()
            colony = AgentColony(_session_database_path(st, base))
            prepare_cano_team(colony, approved=True)
            CollaborativeMission(colony)
            with colony._db() as db:
                db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                           ("resume-after-restart", "Task", "[]", "blocked", "2026-11-04"))
            remote = _snapshot(colony)
            remote["missions"] = [
                {**mission, "status": "running"}
                for mission in remote["missions"]
            ]
            with (patch.dict("os.environ", {
                    "AGENT_COLONY_DB_PATH": base, "APP_AUTH_REQUIRED": "true"}),
                  patch("core.cano_command_center.ColonySnapshotStore") as Store):
                Store.return_value.load.return_value = remote
                render_cano_command_center(
                    st, answer=FakeModel(), owner_key="owner-123",
                    database_url="postgresql://synthetic-test")
                self.assertEqual(st.session_state["_cano_backup_expected"], remote)
                self.assertNotIn("uyușmuyor", " ".join(st.messages))


if __name__ == "__main__":
    unittest.main()
