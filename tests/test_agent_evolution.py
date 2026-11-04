"""Evidence-gated local agent improvements, not autonomous deployment."""
import unittest
from core.agent_evolution import AgentEvaluator, CandidateResult


class AgentEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.evaluator = AgentEvaluator(
            baseline=CandidateResult(name="stable",passed=8,total=10,source_refs=("a",),
                                     reproducible=True,safety_pass=True,benchmark_sha256="a" * 64),
            min_tests=10,
        )

    def test_reproducible_candidate_with_better_score_can_be_proposed(self):
        result = self.evaluator.evaluate(CandidateResult(
            name="candidate", passed=9,total=10,source_refs=("b",),
            reproducible=True,safety_pass=True,benchmark_sha256="a" * 64))
        self.assertEqual(result["status"], "proposal")
        self.assertEqual(result["delta"], 0.1)
        self.assertEqual(result["active"], "stable")
        self.assertEqual(result["candidate"], "candidate")

    def test_rejection_of_weak_unsupported_or_unsafe_versions(self):
        for candidate in (
            CandidateResult("weak",8,10,("b",),True,True,"a" * 64),
            CandidateResult("unsafe",10,10,("b",),True,False,"a" * 64),
            CandidateResult("unreproduced",10,10,("b",),False,True,"a" * 64),
            CandidateResult("unproven",10,10,(),True,True,"a" * 64),
            CandidateResult("tiny",2,2,("b",),True,True,"a" * 64),
        ):
            with self.subTest(candidate=candidate.name):
                self.assertEqual(self.evaluator.evaluate(candidate)["status"], "rejected")
        self.assertEqual(self.evaluator.active.name,"stable")

    def test_proposal_needs_explicit_approval_before_activation(self):
        result=self.evaluator.evaluate(CandidateResult(
            "better",10,10,("evidence:unit-tests",),True,True,"a" * 64))
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

    def test_different_benchmarks_are_not_comparable_even_with_higher_score(self):
        result = self.evaluator.evaluate(CandidateResult(
            "different-easy-exam", 10, 10, ("evidence",), True, True,
            benchmark_sha256="b" * 64))
        self.assertEqual(result["status"], "rejected")
        self.assertEqual(result["reason"], "benchmark_mismatch")
        self.assertIsNone(result["proposal_id"])
        self.assertEqual(self.evaluator.active.name, "stable")

    def test_missing_benchmark_fingerprint_is_not_valid_evidence(self):
        with self.assertRaises(ValueError):
            CandidateResult("missing", 10, 10, ("proof",), True, True,
                            benchmark_sha256="")
        with self.assertRaises(ValueError):
            CandidateResult("malformed", 10, 10, ("proof",), True, True,
                            benchmark_sha256="not-a-sha")

    def test_matching_benchmark_and_improvement_can_be_proposed(self):
        result = self.evaluator.evaluate(CandidateResult(
            "same-exam", 9, 10, ("evidence",), True, True,
            benchmark_sha256="a" * 64))
        self.assertEqual(result["status"], "proposal")
        self.assertEqual(result["benchmark_sha256"], "a" * 64)

    def test_invalid_scores_cannot_become_candidates(self):
        for passed,total in ((11,10),(-1,10),(0,0),(True,10)):
            with self.subTest(passed=passed,total=total):
                with self.assertRaises(ValueError):
                    CandidateResult("bad",passed,total,("source",),True,True,"a" * 64)
