import io
import json
import unittest
from organism_lab.local_candidate_evaluation import evaluate_candidate

class Response:
    def __init__(self, body): self.data=json.dumps({"response":body}).encode()
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def read(self,n=-1): return self.data

def sender(answer):
    return lambda req,timeout: Response(answer)

class CandidateGateTests(unittest.TestCase):
    def test_external_expected_is_required(self):
        res=evaluate_candidate({"type":"unit_conversion","amount":2,"from":"kg","to":"g"},transport=sender('{"answer":2000}'))
        self.assertEqual(res["status"],"unverified")
    def test_accepts_verified_result(self):
        res=evaluate_candidate({"type":"unit_conversion","amount":2,"from":"kg","to":"g"},expected=2000,transport=sender('{"answer":2000}'))
        self.assertEqual(res["status"],"verified")
    def test_denies_wrong_model_answer(self):
        res=evaluate_candidate({"type":"unit_conversion","amount":2,"from":"kg","to":"g"},expected=2000,transport=sender('{"answer":9999}'))
        self.assertEqual(res["status"],"rejected")
    def test_denies_non_json(self):
        res=evaluate_candidate({"type":"csv_mean","values":[1,2,3]},expected=2,transport=sender("the answer is 2"))
        self.assertEqual(res["status"],"rejected")
    def test_unknown_task_never_reaches_model(self):
        def fail(*args,**kwargs): raise AssertionError("network should not be called")
        with self.assertRaises(ValueError): evaluate_candidate({"type":"run_shell","command":"whoami"},transport=fail)
    def test_prompt_removes_answer_leakage(self):
        def check(req,timeout):
            raw=json.loads(req.data.decode())
            self.assertNotIn("expected_patch",raw["prompt"])
            self.assertIn("corrected Python return statement as a JSON string",raw["prompt"])
            return Response('{"answer":"return a+b"}')
        job={"type":"python_bug_fix","source":"def add(a,b):\n return a-b\n","test":"add(2,3)==5","expected_patch":"CHEAT LABEL"}
        res=evaluate_candidate(job,expected="return a+b",transport=check)
        self.assertEqual(res["status"],"verified")
if __name__=="__main__": unittest.main()

class StaticPatchEquivalenceTests(unittest.TestCase):
    def test_whitespace_only_python_patch_is_equivalent(self):
        job={"type":"python_bug_fix","source":"def add(a,b):\n return a-b\n","test":"add(2,3)==5"}
        r=evaluate_candidate(job,expected="return a+b",transport=sender('{"answer":"return a + b"}'))
        self.assertEqual(r["status"],"verified")
    def test_wrong_or_malicious_python_patch_not_accepted(self):
        job={"type":"python_bug_fix","source":"def add(a,b):\n return a-b\n","test":"add(2,3)==5"}
        for answer in ["return a-b","return a+b\\nimport os"]:
            with self.subTest(answer=answer):
                r=evaluate_candidate(job,expected="return a+b",transport=sender(json.dumps({"answer":answer})))
                self.assertEqual(r["status"],"rejected")
