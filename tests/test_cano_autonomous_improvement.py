import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.cano_autonomous_improvement import (
    evaluate_lesson_candidate,
    run_bounded_improvement_cycle,
)
from core.benchmark_harness import BenchmarkCase


LESSON = "Keep answers evidence-based and clearly state uncertainty."


class FakeClient:
    def __init__(self, *, candidate_helps=True):
        self.calls = 0
        self.candidate_helps = candidate_helps

    def chat(self, model, system, prompt):
        self.calls += 1
        if "CANO improvement candidate." in system:
            return LESSON
        if "Critically review" in prompt:
            return "The draft should separate evidence and uncertainty."
        if "Revise your draft" in prompt:
            return "Revision separates evidence and uncertainty."
        if LESSON in prompt and self.candidate_helps:
            return "improved"
        return "baseline"


class BoundedImprovementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.colony = AgentColony(Path(self.temp.name) / "colony.sqlite3")
        self.author = self.colony.create_founder(
            "research", "Separate facts from assumptions.")
        self.colony.grow_specialists(approved=True, batch_size=1)
        self.reviewer = self.colony.get(self.author)["id"]
        with self.colony._db() as db:
            self.reviewer = db.execute(
                "SELECT id FROM colony_agents WHERE id != ? LIMIT 1",
                (self.author,),
            ).fetchone()[0]

    def tearDown(self):
        self.temp.cleanup()

    def cases_json(self):
        import json
        return json.dumps([
            {"case_id": f"case-{i}", "prompt": f"Prompt {i}", "expected": "improved"}
            for i in range(5)
        ])

    def test_cycle_generates_tests_and_saves_only_pending_proposal(self):
        client = FakeClient()
        result = run_bounded_improvement_cycle(
            self.colony, self.author, self.reviewer,
            "Review a short research summary.", self.cases_json(), "safe-v1",
            client=client, model="mock",
        )
        self.assertEqual(result["status"], "review_pending")
        self.assertEqual(result["provider_calls_max"], 24)
        self.assertEqual(client.calls, 24)
        self.assertFalse(result["candidate_activated"])
        self.assertFalse(result["model_weights_updated"])
        self.assertEqual(result["benchmark"]["candidate_passed"], 5)
        self.assertEqual(result["benchmark"]["baseline_passed"], 0)
        self.assertEqual(self.colony.lessons(self.author), [])
        with self.colony._db() as db:
            row = db.execute(
                "SELECT accepted FROM colony_feedback WHERE id=?",
                (result["feedback_id"],),
            ).fetchone()
        self.assertEqual(row["accepted"], 0)
        with self.assertRaises(PermissionError):
            self.colony.approve_feedback(result["feedback_id"])
        approval = self.colony.approve_feedback(
            result["feedback_id"], approved=True)
        self.assertEqual(approval["status"], "accepted")
        self.assertEqual(self.colony.lessons(self.author)[0]["lesson"], LESSON)

    def test_no_measured_gain_never_creates_a_pending_lesson(self):
        client = FakeClient(candidate_helps=False)
        result = run_bounded_improvement_cycle(
            self.colony, self.author, self.reviewer,
            "Review a short research summary.", self.cases_json(), "safe-v1",
            client=client, model="mock",
        )
        self.assertEqual(result["status"], "not_improved")
        self.assertIsNone(result["feedback_id"])
        self.assertEqual(self.colony.lessons(self.author), [])
        self.assertEqual(client.calls, 24)

    def test_candidate_evaluation_requires_five_cases_and_blocks_secret_like_text(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            evaluate_lesson_candidate(
                self.colony, self.author, LESSON,
                (BenchmarkCase("only-one", "prompt", "expected"),),
                client=client, model="mock", dataset_ref="suite",
            )
        secret_cases = tuple(
            BenchmarkCase(f"case-{i}", f"prompt {i}", "expected")
            for i in range(4)
        ) + (BenchmarkCase("case-4", "token AIza" + "a" * 24, "expected"),)
        with self.assertRaises(ValueError):
            evaluate_lesson_candidate(
                self.colony, self.author, LESSON, secret_cases,
                client=client, model="mock", dataset_ref="suite",
            )
        self.assertEqual(client.calls, 0)

    def test_unapproved_candidate_lesson_is_only_temporary_test_context(self):
        client = FakeClient()
        result = evaluate_lesson_candidate(
            self.colony, self.author, LESSON,
            tuple(BenchmarkCase(f"case-{i}", f"Prompt {i}", "improved")
                  for i in range(5)),
            client=client, model="mock", dataset_ref="safe-v1",
        )
        self.assertTrue(result["eligible"])
        self.assertEqual(self.colony.lessons(self.author), [])


if __name__ == "__main__":
    unittest.main()
