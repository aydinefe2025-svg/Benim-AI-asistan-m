import json
import tempfile
import unittest
from pathlib import Path
from core.agent_colony import AgentColony
from core.cano_autonomous_improvement import run_bounded_improvement_cycle

LESSON = "Always check evidence before asserting an experimental result."

class Client:
    def __init__(self, regress=False):
        self.calls=0
        self.regress=regress
    def chat(self, model, system, prompt):
        self.calls+=1
        if "CANO improvement candidate." in system:
            return LESSON
        if "Critically review" in prompt or "Revise your draft" in prompt:
            return "Check evidence."
        if "Holdout question" in prompt and self.regress:
            return "wrong" if LESSON in prompt else "correct"
        return "correct" if LESSON in prompt else "wrong"

def suite(prefix):
    return json.dumps([{"case_id":str(i),"prompt":f"{prefix} question {i}","expected":"correct"} for i in range(5)])

class TwoSuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.colony=AgentColony(Path(self.tmp.name)/"db.sqlite")
        self.author=self.colony.create_founder("research","Check evidence")
        self.reviewer=self.colony.spawn(self.author,"reviewer","Critique",approved=True)
    def run_cycle(self,client,**kwargs):
        return run_bounded_improvement_cycle(self.colony,self.author,self.reviewer,"Review evidence",suite("Training"),"training-v1",client=client,model="fixture",**kwargs)
    def test_single_suite_gain_cannot_create_pending_feedback(self):
        client=Client()
        result=self.run_cycle(client)
        self.assertEqual(result["status"],"holdout_required")
        self.assertIsNone(result["feedback_id"])
        self.assertEqual(client.calls,24)
    def test_holdout_regression_blocks_candidate(self):
        client=Client(regress=True)
        result=self.run_cycle(client,holdout_cases_json=suite("Holdout"),holdout_dataset_ref="holdout-v1")
        self.assertEqual(result["status"],"not_improved")
        self.assertIsNone(result["feedback_id"])
        self.assertEqual(result["holdout_benchmark"]["candidate_passed"],0)
        self.assertEqual(client.calls,44)
    def test_both_suites_pass(self):
        client=Client()
        result=self.run_cycle(client,holdout_cases_json=suite("Holdout"),holdout_dataset_ref="holdout-v1")
        self.assertEqual(result["status"],"review_pending")
        self.assertEqual(client.calls,44)
        with self.colony._db() as db:
            row=db.execute("SELECT evidence,accepted FROM colony_feedback WHERE id=?",(result["feedback_id"],)).fetchone()
        self.assertEqual(row["accepted"],0)
        self.assertIn(result["holdout_benchmark"]["sha256"],row["evidence"])
        self.assertIn(result["benchmark"]["sha256"],row["evidence"])
    def test_overlapping_questions_fail_before_calls(self):
        client=Client()
        with self.assertRaises(ValueError):
            self.run_cycle(client,holdout_cases_json=suite("Training"),holdout_dataset_ref="holdout-v1")
        self.assertEqual(client.calls,0)
