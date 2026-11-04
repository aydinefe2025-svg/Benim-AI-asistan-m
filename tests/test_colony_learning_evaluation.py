import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony


class LearningEvaluationTests(unittest.TestCase):
    def test_evidence_is_distinct_and_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.db")
            founder = colony.create_founder("founder", "Research carefully")
            self.assertFalse(colony.evaluate_learning(founder)["retrieval_ready"])
            colony.feedback(founder, "task1", "lesson1", "source-a", accepted=True)
            colony.feedback(founder, "task2", "lesson2", "source-a", accepted=True)
            colony.feedback(founder, "task3", "lesson3", "source-b", accepted=False)
            state = colony.evaluate_learning(founder)
            self.assertEqual(state["accepted_lessons"], 2)
            self.assertEqual(state["distinct_evidence"], 1)
            self.assertFalse(state["retrieval_ready"])
            colony.feedback(founder, "task4", "lesson4", "source-b", accepted=True)
            self.assertTrue(colony.evaluate_learning(founder)["retrieval_ready"])
            self.assertFalse(colony.evaluate_learning(founder)["model_weights_updated"])

    def test_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "colony.db")
            founder = colony.create_founder("founder", "Instructions")
            with self.assertRaises(ValueError):
                colony.evaluate_learning(founder, min_evidence=0)
            with self.assertRaises(KeyError):
                colony.evaluate_learning("unknown")


if __name__ == "__main__":
    unittest.main()
