import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from core.agent_colony import AgentColony
from core.task_panel import _session_database_path
from core.cano_command_center import (
    prepare_cano_team, read_cano_status, render_cano_command_center,
    _render_claim_evidence_review,
)


class FakeStreamlit:
    def __init__(self, *, clicks=None, submit=False, task="", crossref=False, local_backup=False,\n                 checkbox_values=None, select_values=None):
        self.session_state = {}
        self.clicks = set(clicks or [])
        self.submit = submit
        self.task = task
        self.crossref = crossref
        self.local_backup = local_backup
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

    def text_input(self, label, **kw):
        return self.session_state.get(kw.get("key", ""), "")

    def checkbox(self, label, **kw):
        if kw.get("key") == "cano_local_backup_opt_in":
            return self.session_state.get("cano_local_backup_opt_in", self.local_backup)
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


class StrictWidgetState(dict):
    """Emulates Streamlit rejecting widget-key writes after instantiation."""
    def __init__(self):
        super().__init__()
        self.blocked = set()

    def __setitem__(self, key, value):
        if key in self.blocked:
            raise RuntimeError("StreamlitWidgetAlreadyInstantiatedError: " + key)
        super().__setitem__(key, value)


class StrictStreamlit(FakeStreamlit):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session_state = StrictWidgetState()

    def checkbox(self, label, **kwargs):
        value = super().checkbox(label, **kwargs)
        key = kwargs.get("key")
        if key:
            self.session_state.blocked.add(key)
        return value

    def rerun(self):
        # The next execution is allowed to set widget state before rendering.
        self.session_state.blocked.clear()
        super().rerun()


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
        browser_patch = patch("core.cano_command_center.browser_colony_component", return_value=None)
        self.browser_component = browser_patch.start()
        self.addCleanup(browser_patch.stop)

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

    def test_explicit_task_dois_precede_crossref_matches_in_the_real_cockpit(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"}, crossref=True)
        model = FakeModel()
        goal = ("BMJ study DOI 10.1136/bmj-2023-075847; correction "
                "10.1136/bmj.q1024")
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}), \
                patch("core.cano_command_center.scientific_sources", return_value=[
                    {"title": "Wrong relevance match",
                     "url": "https://doi.org/10.64239/pi-tr-qt4802"}]):
            render_cano_command_center(st, answer=model)
            st.task, st.submit = goal, True
            render_cano_command_center(st, answer=model)
            colony = AgentColony(_session_database_path(st, self.db_base))
            from core.collaborative_mission import CollaborativeMission
            mission = CollaborativeMission(colony).get(
                read_cano_status(colony)["history"][0]["id"])
        self.assertEqual(
            [item["url"] for item in mission["stages"][0]["source_leads"]],
            ["https://doi.org/10.1136/bmj-2023-075847",
             "https://doi.org/10.1136/bmj.q1024",
             "https://doi.org/10.64239/pi-tr-qt4802"],
        )

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

    def test_cockpit_resumes_a_blocked_mission_without_repeating_saved_stages(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        calls = []
        def fail_once(prompt):
            calls.append(prompt)
            if len(calls) == 4:
                raise RuntimeError("temporary provider interruption")
            return f"Stage {len(calls)}"

        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            st.task = "Resume safely from the cockpit"
            st.submit = True
            render_cano_command_center(st, answer=fail_once)

            colony = AgentColony(_session_database_path(st, self.db_base))
            from core.collaborative_mission import CollaborativeMission
            mission = CollaborativeMission(colony).interrupted()[0]
            saved = CollaborativeMission(colony).get(mission["id"])
            self.assertEqual(saved["status"], "blocked")
            self.assertEqual([stage["role"] for stage in saved["stages"]],
                             ["planner", "researcher", "reviewer"])

            # The main cockpit offers the resume control without requiring the
            # user to navigate to the sidebar specialist-agent panel.
            st.clicks.add("cano_resume_partial_" + mission["id"])
            render_cano_command_center(st, answer=fail_once)

            finished = CollaborativeMission(colony).get(mission["id"])
            self.assertEqual(finished["status"], "review_pending")
            self.assertEqual([stage["role"] for stage in finished["stages"]],
                             ["planner", "researcher", "reviewer", "synthesis"])
            self.assertEqual(len(calls), 5)
            self.assertIn("kaldığı yerden tamamlandı", " ".join(st.messages))

    def test_cockpit_resume_provider_error_is_shown_without_traceback(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        calls = []

        def fail_after_three(prompt):
            calls.append(prompt)
            if len(calls) >= 4:
                raise RuntimeError("private provider response body")
            return f"Stage {len(calls)}"

        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            st.task = "Resume a blocked task safely"
            st.submit = True
            render_cano_command_center(st, answer=fail_after_three)

            colony = AgentColony(_session_database_path(st, self.db_base))
            from core.collaborative_mission import CollaborativeMission
            manager = CollaborativeMission(colony)
            mission = manager.interrupted()[0]
            st.clicks.add("cano_resume_partial_" + mission["id"])
            render_cano_command_center(st, answer=fail_after_three)

            saved = manager.get(mission["id"])

        messages = " ".join(st.messages)
        self.assertIn(
            "Görev durdu: model sağlayıcı çağrısı, synthesis rolü", messages)
        self.assertNotIn("private provider response body", messages)
        self.assertNotIn("NameError", messages)
        self.assertNotIn("Traceback", messages)
        self.assertEqual(saved["status"], "blocked")
        self.assertEqual(len(saved["stages"]), 3)
        self.assertEqual(len(calls), 5)

    def test_resume_backup_checkpoint_failure_stops_before_provider_call(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"})
        calls = []

        def interrupted(prompt):
            calls.append(prompt)
            if len(calls) >= 4:
                raise RuntimeError("PRIVATE provider response")
            return f"Stage {len(calls)}"

        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            st.task = "Preserve a blocked mission on backup failure"
            st.submit = True
            render_cano_command_center(st, answer=interrupted)

            colony = AgentColony(_session_database_path(st, self.db_base))
            from core.cano_command_center import _snapshot
            from core.collaborative_mission import CollaborativeMission
            manager = CollaborativeMission(colony)
            mission = manager.interrupted()[0]
            before = manager.get(mission["id"])
            self.assertEqual(before["status"], "blocked")
            self.assertEqual(len(before["stages"]), 3)
            st.clicks.add("cano_resume_partial_" + mission["id"])

            from core.colony_postgres import ColonySnapshotStore
            with (patch.object(ColonySnapshotStore, "__init__", return_value=None),
                  patch.object(ColonySnapshotStore, "verify_schema"),
                  patch.object(ColonySnapshotStore, "load",
                               return_value=_snapshot(colony)),
                  patch.object(ColonySnapshotStore, "save_versioned_verified",
                               side_effect=RuntimeError("PRIVATE revision limit")) as save):
                render_cano_command_center(
                    st, answer=interrupted, owner_key="owner-a",
                    database_url="postgresql://synthetic-test")

            save.assert_called_once()

        messages = " ".join(st.messages)
        self.assertIn("görev sürdürülmedi", messages)
        self.assertIn("sağlayıcı çağrısı yapılmadı", messages)
        self.assertNotIn("PRIVATE", messages)
        self.assertNotIn("Traceback", messages)
        after = manager.get(mission["id"])
        self.assertEqual(after["status"], "blocked")
        self.assertEqual(len(after["stages"]), 3)
        self.assertEqual(len(calls), 4)

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
                reader.assert_called_once_with("10.1234/solar", query="Solar study")
            render_cano_command_center(st, answer=FakeModel())
            self.assertIn("Measured solar output", " ".join(st.messages))
            saved = CollaborativeMission(colony).get(mission["id"])
            self.assertEqual(saved["stages"][0]["source_documents"][0]["status"],
                             "full_text_excerpt")
            self.assertFalse(saved["stages"][0]["source_documents"][0]["claim_verified"])

    def test_owner_claim_review_is_explicit_and_does_not_complete_mission(self):
        import json
        from core.collaborative_mission import CollaborativeMission

        st = FakeStreamlit(clicks={"cano_prepare_team"})
        rationale = ("I inspected the publisher full text and confirmed that the "
                     "quoted measurement directly supports this narrow claim.")
        st.task = rationale
        reviewer = "oidc_" + "a" * 64
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            colony = AgentColony(_session_database_path(st, self.db_base))
            prepare_cano_team(colony, approved=True)
            manager = CollaborativeMission(colony)
            mission = manager.execute(
                "Solar study: the paper measured solar output.",
                client=type("Client", (), {
                    "chat": lambda self, model, system, prompt: "Draft"
                })(), model="test",
                source_lookup=lambda query, limit=3: [
                    {"title": "Solar study", "url": "https://doi.org/10.1234/solar"}])
            with patch("core.europepmc_evidence.read_publication_evidence",
                       return_value={"doi": "10.1234/solar", "title": "Solar study",
                                     "url": "https://europepmc.org/articles/PMC1234567",
                                     "status": "full_text_excerpt",
                                     "excerpt": "Measured solar output in a real study.",
                                     "claim_verified": False}):
                manager.inspect_source_documents(mission["id"])

            class AuditModel:
                def __init__(self):
                    self.calls = 0

                def __call__(self, prompt):
                    self.calls += 1
                    return json.dumps({"claims": [{
                        "claim": "The study measured solar output.",
                        "doi": "10.1234/solar",
                        "quote": "Measured solar output in a real study.",
                        "comparison": "supports",
                        "rationale": "The passage directly reports a measurement.",
                    }]})

            model = AuditModel()
            audit_key = "cano_claim_audit_external_consent_" + mission["id"]
            st.checkbox_values[audit_key] = True
            st.submit = True
            checkpoints = []
            planner = manager.get(mission["id"])["stages"][0]
            _render_claim_evidence_review(
                st, manager, mission["id"], planner, owner_key=reviewer,
                answer=model, checkpoint=lambda **kwargs: checkpoints.append(kwargs))
            audited = manager.get(mission["id"])
            item = audited["stages"][0]["source_claim_audit"][0]
            self.assertEqual(item["status"], "quote_found_unverified")
            self.assertFalse(item["claim_verified"])
            self.assertEqual(model.calls, 1)

            decision_key = "cano_claim_decision_" + mission["id"] + "_0"
            primary_key = "cano_claim_primary_" + mission["id"] + "_0"
            st.select_values[decision_key] = "Birincil tam metin doğrudan destekliyor"
            st.checkbox_values[primary_key] = True
            st.submit = True
            planner = audited["stages"][0]
            _render_claim_evidence_review(
                st, manager, mission["id"], planner, owner_key=reviewer,
                answer=model, checkpoint=lambda **kwargs: checkpoints.append(kwargs))
            reviewed = manager.get(mission["id"])
            claim = reviewed["stages"][0]["source_claim_audit"][0]
            self.assertTrue(claim["claim_verified"])
            self.assertEqual(claim["human_review"]["reviewer_id"], reviewer)
            self.assertTrue(claim["human_review"]["primary_source_confirmed"])
            self.assertEqual(reviewed["status"], "review_pending")
            self.assertEqual(model.calls, 1)
            self.assertEqual(len(checkpoints), 3)

    def test_opted_in_browser_backup_survives_new_session_and_no_provider_replay(self):
        st = FakeStreamlit(clicks={"cano_prepare_team"}, local_backup=True)
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            render_cano_command_center(st, answer=FakeModel())
            initial_write = self.browser_component.call_args.kwargs["write"]
            self.assertIsNotNone(initial_write)
            self.assertEqual(len(initial_write["token"]), 64)
            report = {"status": "ok", "payload": initial_write["payload"],
                      "ack": initial_write["token"]}
            self.browser_component.return_value = report
            render_cano_command_center(st, answer=FakeModel())
            self.assertIn("geri okunarak doğrulandı", " ".join(st.messages))
            # Hard browser refresh creates a new Streamlit session state and ID.
            st2 = FakeStreamlit()
            model = FakeModel()
            render_cano_command_center(st2, answer=model)
            self.assertIn("geri yüklendi", " ".join(st2.messages))
            render_cano_command_center(st2, answer=model)
            self.assertEqual(st2.metrics["Uzman"], 7)
            self.assertEqual(len(model.calls), 0)
            self.assertTrue(st2.session_state["cano_local_backup_opt_in"])
            # An unrelated user's browser must not receive another browser's backup.
            self.browser_component.return_value = None
            st3 = FakeStreamlit()
            render_cano_command_center(st3, answer=model)
            self.assertEqual(st3.metrics["Uzman"], 0)

    def test_authenticated_empty_session_automatically_restores_owner_backup(self):
        from core.colony_postgres import ColonySnapshotStore
        st = FakeStreamlit()
        saved = {
            "agents": [{
                "id": "saved-agent", "parent_id": None, "generation": 0,
                "role": "research", "instructions": "Research",
                "state": "active", "created_at": "2026-11-04"}],
            "feedback": [], "reviews": [], "missions": []
        }
        with (patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}),
              patch.object(ColonySnapshotStore, "__init__", return_value=None),
              patch.object(ColonySnapshotStore, "verify_schema"),
              patch.object(ColonySnapshotStore, "load", return_value=saved)):
            render_cano_command_center(
                st, owner_key="owner", database_url="postgresql://synthetic")
        self.assertIn("geri yüklendi", " ".join(st.messages).lower())
        self.assertEqual(st.session_state["_cano_backup_expected"], saved)
        local = AgentColony(_session_database_path(st, self.db_base))
        with local._db() as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM colony_agents").fetchone()[0], 1)
        self.assertIn("rerun", st.messages)

    def test_authenticated_account_never_reads_anonymous_local_backup(self):
        st = FakeStreamlit(local_backup=True)
        with patch.dict("os.environ", {
                "AGENT_COLONY_DB_PATH": self.db_base, "APP_AUTH_REQUIRED": "true"}):
            render_cano_command_center(st, answer=FakeModel())
            self.browser_component.assert_not_called()
            self.assertEqual(st.metrics["Uzman"], 0)

    def test_browser_restore_does_not_mutate_instantiated_checkbox(self):
        from core.browser_colony import encode_browser_colony_backup
        from core.cano_command_center import _snapshot
        source = AgentColony(Path(self.tmp.name) / "existing.sqlite3")
        source.create_founder("research", "Research")
        source.grow_specialists(approved=True)
        write = encode_browser_colony_backup(_snapshot(source))
        self.browser_component.return_value = {
            "status": "ok", "payload": write["payload"], "ack": write["token"]
        }
        st = StrictStreamlit()
        with patch.dict("os.environ", {
                "AGENT_COLONY_DB_PATH": self.db_base, "APP_AUTH_REQUIRED": ""}):
            render_cano_command_center(st, answer=FakeModel())
            self.assertIn("geri yüklendi", " ".join(st.messages))
            render_cano_command_center(st, answer=FakeModel())
            self.assertTrue(st.session_state["cano_local_backup_opt_in"])
            self.assertEqual(st.metrics["Uzman"], 4)

    def test_browser_clear_does_not_mutate_instantiated_checkbox(self):
        st = StrictStreamlit(clicks={"cano_local_backup_clear"})
        st.session_state["cano_local_backup_opt_in"] = True
        self.browser_component.return_value = {
            "status":"ok", "payload":"", "ack":"cleared"}
        with patch.dict("os.environ", {
                "AGENT_COLONY_DB_PATH": self.db_base, "APP_AUTH_REQUIRED": ""}):
            render_cano_command_center(st, answer=FakeModel())
            st.session_state.blocked.clear()
            render_cano_command_center(st, answer=FakeModel())
            self.assertFalse(st.session_state["cano_local_backup_opt_in"])
            self.assertTrue(self.browser_component.call_args.kwargs["write"] is None)

    def test_malformed_browser_backup_does_not_create_agents(self):
        self.browser_component.return_value = {"status":"ok","payload":"{}"}
        st = FakeStreamlit()
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            render_cano_command_center(st, answer=FakeModel())
            self.assertEqual(st.metrics["Uzman"], 0)
            self.assertIn("doğrulanamadı", " ".join(st.messages))

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
              patch.object(ColonySnapshotStore, "__init__", return_value=None),
              patch.object(ColonySnapshotStore, "verify_schema") as setup,
              patch.object(ColonySnapshotStore, "load", return_value=None),
              patch.object(ColonySnapshotStore, "save_versioned_verified",
                           return_value=True) as save):
            render_cano_command_center(
                st, answer=model, owner_key="authenticated-owner",
                database_url="postgresql://synthetic-test")
            self.assertGreaterEqual(save.call_count, 1, msg=repr(st.messages))
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
            # Every stage is archived remotely BEFORE a later model call.
            # The final duplicate checkpoint records review_pending state.
            import json
            stage_counts = [
                len(json.loads(call.args[1]["missions"][0]["stages"]))
                for call in save.call_args_list if call.args[1]["missions"]]
            self.assertEqual(stage_counts, [1, 2, 3, 4, 4])
            archive_flags = [
                call.kwargs.get("archive_prior") for call in save.call_args_list
                if call.args[1]["missions"]]
            self.assertEqual(archive_flags, [True, False, False, False, False])
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
              patch.object(ColonySnapshotStore, "__init__", return_value=None),
              patch.object(ColonySnapshotStore, "verify_schema"),
              patch.object(ColonySnapshotStore, "load", return_value=None),
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
            stage_counts = [
                len(__import__("json").loads(call.args[1]["missions"][0]["stages"]))
                for call in save.call_args_list if call.args[1]["missions"]]
            self.assertEqual(stage_counts, [1, 2, 3, 3])
            archive_flags = [
                call.kwargs.get("archive_prior") for call in save.call_args_list
                if call.args[1]["missions"]]
            self.assertEqual(archive_flags, [True, False, False, False])

    def test_unavailable_authenticated_backup_blocks_billable_mission(self):
        """Fail before model calls when durable backing store is unavailable."""
        from core.colony_postgres import ColonySnapshotStore
        st = FakeStreamlit()
        model = FakeModel()
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            colony = AgentColony(_session_database_path(st, self.db_base))
            prepare_cano_team(colony, approved=True)
            st.task, st.submit = "Run with no durable DB", True
            with (patch.object(ColonySnapshotStore, "__init__", return_value=None),
                  patch.object(ColonySnapshotStore, "verify_schema",
                               side_effect=RuntimeError("secret PostgreSQL URL password"))):
                render_cano_command_center(
                    st, answer=model, owner_key="owner",
                    database_url="postgresql://synthetic-test")
        self.assertEqual(model.calls, [])
        self.assertNotIn("password", " ".join(st.messages))
        self.assertIn("PostgreSQL", " ".join(st.messages))



    def test_cano_prioritizes_both_explicit_dois_over_crossref_candidates(self):
        from core.collaborative_mission import CollaborativeMission
        goal = ("Read DOI 10.1136/bmj-2023-075847; correction DOI "
                "10.1136/bmj.q1024.")
        unrelated = [{"title": "Unrelated result",
                      "url": "https://doi.org/10.64239/pi-tr-qt4802"}]
        st = FakeStreamlit(clicks={"cano_prepare_team"}, task=goal, crossref=True)
        model = FakeModel()
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            with patch("core.cano_command_center.scientific_sources",
                       return_value=unrelated) as crossref:
                render_cano_command_center(st, answer=model)
                st.submit = True
                render_cano_command_center(st, answer=model)
                colony = AgentColony(_session_database_path(st, self.db_base))
                mission = CollaborativeMission(colony).get(
                    read_cano_status(colony)["history"][0]["id"])
        crossref.assert_called()
        self.assertEqual(
            [x["url"] for x in mission["stages"][0]["source_leads"][:2]],
            ["https://doi.org/10.1136/bmj-2023-075847",
             "https://doi.org/10.1136/bmj.q1024"])
        self.assertEqual(len(model.calls), 4)

    def test_user_supplied_dois_do_not_require_crossref_opt_in(self):
        from core.collaborative_mission import CollaborativeMission
        goal = ("Read DOI 10.1136/bmj-2023-075847; correction DOI "
                "10.1136/bmj.q1024.")
        st = FakeStreamlit(clicks={"cano_prepare_team"}, task=goal, crossref=False)
        model = FakeModel()
        with patch.dict("os.environ", {"AGENT_COLONY_DB_PATH": self.db_base}):
            with patch("core.cano_command_center.scientific_sources") as crossref:
                render_cano_command_center(st, answer=model)
                st.submit = True
                render_cano_command_center(st, answer=model)
                colony = AgentColony(_session_database_path(st, self.db_base))
                mission = CollaborativeMission(colony).get(
                    read_cano_status(colony)["history"][0]["id"])
        crossref.assert_not_called()
        self.assertEqual(
            [x["url"] for x in mission["stages"][0]["source_leads"][:2]],
            ["https://doi.org/10.1136/bmj-2023-075847",
             "https://doi.org/10.1136/bmj.q1024"])
        self.assertEqual(len(model.calls), 4)


if __name__ == "__main__":
    unittest.main()
