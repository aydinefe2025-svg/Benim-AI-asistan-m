"""Evidence-gated local agent improvements, not autonomous deployment."""
import unittest
from core.agent_evolution import AgentEvaluator, CandidateResult


class AgentEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = AgentEvaluator(
            baseline=CandidateResult(name="stable",passed=8,total=10,source_refs=("a",),
                                     reproducible=True,safety_pass=True),
            min_tests=10,
        )

    def test_reproducible_candidate_with_better_score_can_be_proposed(self):
        result = self.evaluator.evaluate(CandidateResult(
            name="candidate", passed=9,total=10,source_refs=("b",),
            reproducible=True,safety_pass=True))
        self.assertEqual(result["status"], "proposal")
        self.assertEqual(result["delta"], 0.1)
        self.assertEqual(result["active"], "stable")
        self.assertEqual(result["candidate"], "candidate")

    def test_rejection_of_weak_unsupported_or_unsafe_versions(self):
        for candidate in (
            CandidateResult("weak",8,10,("b",),True,True),
            CandidateResult("unsafe",10,10,("b",),True,False),
            CandidateResult("unreproduced",10,10,("b",),False,True),
            CandidateResult("unproven",10,10,(),True,True),
            CandidateResult("tiny",2,2,("b",),True,True),
        ):
            with self.subTest(candidate=candidate.name):
                self.assertEqual(self.evaluator.evaluate(candidate)["status"], "rejected")
        self.assertEqual(self.evaluator.active.name,"stable")

    def test_proposal_needs_explicit_approval_before_activation(self):
        result=self.evaluator.evaluate(CandidateResult(
            "better",10,10,("evidence:unit-tests",),True,True))
        with self.assertRaises(PermissionError):
            self.evaluator.approve(result["proposal_id"], approved=False)
        self.assertEqual(self.evaluator.active.name,"stable")
        activated=self.evaluator.approve(result["proposal_id"],approved=True)
        self.assertEqual(activated["active"],"better")
        self.assertEqual(self.evaluator.active.name,"better")
        self.assertEqual(self.evaluator.rollback(approved=True)["active"],"stable")

    def test_unknown_proposal_and_unapproved_rollback_fail_closed(self):
        with self.assertRaises(KeyError):
            self.evaluator.approve("nonexistent",approved=True)
        with self.assertRaises(PermissionError):
            self.evaluator.rollback(approved=False)
        self.assertEqual(self.evaluator.active.name,"stable")

    def test_invalid_scores_cannot_become_candidates(self):
        for passed,total in ((11,10),(-1,10),(0,0),(True,10)):
            with self.subTest(passed=passed,total=total):
                with self.assertRaises(ValueError):
                    CandidateResult("bad",passed,total,("source",),True,True)
