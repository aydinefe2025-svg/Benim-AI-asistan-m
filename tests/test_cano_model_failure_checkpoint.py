"""Regression: a failed third model stage is durably saved as blocked.

A PostgreSQL snapshot copy is emulated by copying the actual colony snapshot
after each callback. This exercises the real four-stage runner without a real
LLM call or database credential.
"""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from core.agent_colony import AgentColony
from core.cano_command_center import _snapshot
from core.collaborative_mission import CollaborativeMission
from core.colony_restore import restore_empty_colony


class RateLimitedThirdStage:
    def __init__(self):
        self.calls = 0

    def chat(self, model, system, prompt):
        self.calls += 1
        if self.calls == 3:
            raise RuntimeError("rate_limit_exceeded")
        return "Verified synthetic stage " + str(self.calls)


class ModelFailureCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.colony = AgentColony(Path(self.temporary.name) / "colony.sqlite3")
        self.colony.create_founder("research", "Research carefully")
        self.colony.grow_specialists(approved=True)
        self.mission = CollaborativeMission(self.colony)

    def test_failed_model_call_saves_blocked_status_with_prior_two_stages(self):
        client = RateLimitedThirdStage()
        remote_snapshots = []
        statuses = []
        counts = []

        def checkpoint():
            # Simulate successful owner-postgres CAS/save/readback of real data.
            content = deepcopy(_snapshot(self.colony))
            remote_snapshots.append(content)
            last = content["missions"][-1]
            statuses.append(last["status"])
            counts.append(len(json.loads(last["stages"])))

        with self.assertRaisesRegex(RuntimeError, "rate_limit_exceeded"):
            self.mission.execute(
                "A real user mission", client=client, model="fake",
                on_checkpoint=checkpoint,
            )

        self.assertEqual(client.calls, 3)  # No retry of the failed call.
        self.assertEqual(statuses, ["running", "running", "blocked"])
        self.assertEqual(counts, [1, 2, 2])
        # The last remotely persisted record is resumable after a new session.
        restored = AgentColony(Path(self.temporary.name) / "restored.sqlite3")
        restore_empty_colony(restored, remote_snapshots[-1])
        rows = CollaborativeMission(restored).interrupted()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertEqual(
            [s["role"] for s in CollaborativeMission(restored).get(rows[0]["id"])["stages"]],
            ["planner", "researcher"],
        )

    def test_failed_backup_of_blocked_status_never_retries_provider(self):
        client = RateLimitedThirdStage()
        seen = []

        def checkpoint():
            with self.colony._db() as db:
                row = db.execute("SELECT status FROM colony_missions LIMIT 1").fetchone()
            seen.append(row["status"])
            if row["status"] == "blocked":
                raise RuntimeError("remote CAS unavailable")

        with self.assertRaisesRegex(RuntimeError, "rate_limit_exceeded"):
            self.mission.execute(
                "A real user mission", client=client, model="fake",
                on_checkpoint=checkpoint,
            )
        self.assertEqual(client.calls, 3)
        self.assertEqual(seen, ["running", "running", "blocked"])
        self.assertEqual(self.mission.interrupted()[0]["status"], "blocked")

    def test_postgres_checkpoint_error_does_not_get_second_write_attempt(self):
        client = RateLimitedThirdStage()
        states = []

        def checkpoint():
            states.append(len(states))
            if len(states) == 2:
                raise RuntimeError("PostgreSQL checkpoint failure")

        with self.assertRaisesRegex(RuntimeError, "PostgreSQL checkpoint failure"):
            self.mission.execute(
                "A real user mission", client=client, model="fake",
                on_checkpoint=checkpoint,
            )
        self.assertEqual(states, [0, 1])
        self.assertEqual(client.calls, 2)
        self.assertEqual(self.mission.interrupted()[0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
