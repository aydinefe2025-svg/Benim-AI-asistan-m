import tempfile
from datetime import datetime, timedelta, timezone
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission


class FakeClient:
    def __init__(self):
        self.calls = []

    def chat(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        return "Result " + str(len(self.calls))


class CollaborativeMissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.colony = AgentColony(Path(self.tmp.name) / "colony.sqlite3")
        self.colony.create_founder("research", "Research carefully")
        self.colony.grow_specialists(approved=True)
        self.missions = CollaborativeMission(self.colony)

    def test_every_role_records_text_only_execution_boundary_after_restore(self):
        from core.cano_command_center import _snapshot
        from core.colony_restore import restore_empty_colony
        client = FakeClient()
        result = self.missions.execute(
            "Calculate 2+2; do not invent performed experiments", client=client, model="fake")
        for _, _, prompt in client.calls:
            self.assertIn("No code, calculator, device or experiment is executed", prompt)
            self.assertIn("not execution receipts", prompt)
        restored = AgentColony(Path(self.tmp.name) / "restored.sqlite3")
        restore_empty_colony(restored, _snapshot(self.colony))
        saved = CollaborativeMission(restored).get(result["id"])
        self.assertEqual(saved["status"], "review_pending")
        self.assertEqual([s["execution_mode"] for s in saved["stages"]],
                         ["model_text_only"] * 4)

    def test_four_calls_and_persisted_review_pending(self):
        client = FakeClient()
        result = self.missions.execute("Investigate solar energy", client=client, model="fake")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(len(client.calls), 4)
        self.assertEqual([s["role"] for s in result["stages"]],
                         ["planner", "researcher", "reviewer", "synthesis"])
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(self.missions.get(result["id"])["stages"], result["stages"])
        self.assertIn("Result 2", client.calls[2][2])
        self.assertIn("Result 3", client.calls[3][2])

    def test_accepted_lesson_is_retrieved_by_the_next_team_mission(self):
        founder = self.colony.get(self.missions._agents()[0])["id"]
        self.colony.feedback(
            founder, "Earlier source review", "Prefer primary evidence",
            "review:accepted-17", accepted=True)
        self.colony.feedback(
            founder, "Earlier source review", "Guess a citation when needed",
            "review:rejected-18", accepted=False)
        client = FakeClient()

        result = self.missions.execute(
            "Investigate a new energy question", client=client, model="fake")

        self.assertEqual(result["status"], "review_pending")
        self.assertIn("Prefer primary evidence", client.calls[0][2])
        self.assertIn("Prefer primary evidence", client.calls[1][2])
        self.assertNotIn("Guess a citation when needed", repr(client.calls))

    def test_external_checkpoint_runs_after_each_durable_stage_before_next_model_call(self):
        client = FakeClient()
        seen = []
        def checkpoint():
            with self.colony._db() as db:
                rows = db.execute("SELECT id FROM colony_missions").fetchall()
            self.assertEqual(len(rows), 1)
            saved = self.missions.get(rows[0]["id"])
            self.assertEqual(len(saved["stages"]), len(client.calls))
            self.assertEqual(saved["status"], "running")
            seen.append(len(saved["stages"]))
        result = self.missions.execute(
            "Research safely", client=client, model="fake",
            on_checkpoint=checkpoint)
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(seen, [1, 2, 3, 4])
        self.assertEqual(len(client.calls), 4)

    def test_checkpoint_failure_prevents_any_additional_model_calls(self):
        client = FakeClient()
        seen = []
        def checkpoint():
            seen.append(len(client.calls))
            if len(seen) == 2:
                raise RuntimeError("Durable remote write failed")
        with self.assertRaisesRegex(RuntimeError, "Durable remote write failed"):
            self.missions.execute(
                "Research safely", client=client, model="fake",
                on_checkpoint=checkpoint)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(seen, [1, 2])
        interrupted = self.missions.interrupted()
        self.assertEqual(len(interrupted), 1)
        self.assertEqual(len(self.missions.get(interrupted[0]["id"])["stages"]), 2)

    def test_explicit_crossref_metadata_leads_are_checkpointed(self):
        calls = []
        def lookup(query, limit=3):
            calls.append((query, limit))
            return [{"title": "Solar PV technology", "url": "https://doi.org/10.1234/abc",
                     "doi": "10.1234/abc", "verified": False}]
        client = FakeClient()
        result = self.missions.execute(
            "Investigate solar PV", client=client, model="fake",
            source_lookup=lookup)
        self.assertEqual(calls, [("Investigate solar PV", 3)])
        self.assertEqual(len(client.calls), 4)
        self.assertEqual(result["stages"][0]["source_lookup_status"], "metadata_only")
        self.assertEqual(result["stages"][0]["source_leads"][0]["url"],
                         "https://doi.org/10.1234/abc")
        self.assertFalse(result["stages"][0]["source_leads"][0]["verified"])
        self.assertIn("https://doi.org/10.1234/abc", client.calls[1][2])
        self.assertEqual(self.missions.get(result["id"])["stages"], result["stages"])

    def test_no_crossref_call_by_default_and_failure_does_not_fake_sources(self):
        client = FakeClient()
        result = self.missions.execute("Private research", client=client, model="fake")
        self.assertNotIn("source_leads", result["stages"][0])

        def offline(query, limit=3):
            raise TimeoutError("Crossref unavailable")
        second = self.missions.execute("Public research", client=FakeClient(),
                                       model="fake", source_lookup=offline)
        self.assertEqual(second["status"], "review_pending")
        self.assertEqual(second["stages"][0]["source_lookup_status"], "unavailable")
        self.assertEqual(second["stages"][0]["source_leads"], [])

    def test_reject_untrusted_candidate_urls_and_claimed_verification(self):
        def bad(query, limit=3):
            return [{"title":"Bad link", "url":"http://private.local/admin",
                     "verified":True},
                    {"title":"Paper", "url":"https://doi.org/10.1234/good",
                     "verified":True}]
        record = self.missions.execute("Research", client=FakeClient(),
                                       model="fake", source_lookup=bad)
        leads = record["stages"][0]["source_leads"]
        self.assertEqual(len(leads), 1)
        self.assertEqual(leads[0]["url"], "https://doi.org/10.1234/good")
        self.assertFalse(leads[0]["verified"])

    def test_requires_reviewer_and_nonempty_task(self):
        with self.assertRaises(ValueError):
            self.missions.execute(" ", client=FakeClient(), model="fake")
        with self.colony._db() as db:
            db.execute("UPDATE colony_agents SET state='inactive' WHERE role='evidence-reviewer'")
        with self.assertRaises(RuntimeError):
            self.missions.execute("Valid", client=FakeClient(), model="fake")

    def test_model_failure_checkpoints_and_resume_skips_completed_stages(self):
        class FailingOnce:
            def __init__(self):
                self.calls = 0

            def chat(self, model, system, prompt):
                self.calls += 1
                if self.calls == 3:
                    raise RuntimeError("Provider down")
                return "Result " + str(self.calls)

        client = FailingOnce()
        with self.assertRaises(RuntimeError):
            self.missions.execute("Valid", client=client, model="fake")
        interrupted = self.missions.interrupted()
        self.assertEqual(len(interrupted), 1)
        self.assertEqual(interrupted[0]["status"], "blocked")
        partial = self.missions.get(interrupted[0]["id"])
        self.assertEqual([s["role"] for s in partial["stages"]],
                         ["planner", "researcher"])
        result = self.missions.resume(partial["id"], client=client, model="fake")
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(result["model_calls"], 2)
        self.assertEqual(client.calls, 5)
        self.assertEqual([s["output"] for s in result["stages"][:2]],
                         ["Result 1", "Result 2"])
        self.assertEqual(self.missions.resume(partial["id"], client=client,
                                               model="fake")["model_calls"], 0)
        self.assertEqual(client.calls, 5)
        self.assertEqual(self.missions.interrupted(), [])

    def test_stale_running_requires_recovery_before_resume(self):
        mission_id = "running-test"
        old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       (mission_id, "Valid", "[]", "running", old_time))
        with self.assertRaises(RuntimeError):
            self.missions.resume(mission_id, client=FakeClient(), model="fake")
        recovered = self.missions.recover_stale(older_than_seconds=3600)
        self.assertEqual(recovered, [mission_id])
        result = self.missions.resume(mission_id, client=FakeClient(), model="fake")
        self.assertEqual(result["model_calls"], 4)
        self.assertEqual(result["status"], "review_pending")

    def test_recent_running_not_recovered_and_threshold_validated(self):
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       ("recent", "Valid", "[]", "running",
                        datetime.now(timezone.utc).isoformat()))
        self.assertEqual(self.missions.recover_stale(), [])
        with self.assertRaises(ValueError):
            self.missions.recover_stale(older_than_seconds=30)


if __name__ == "__main__":
    unittest.main()
