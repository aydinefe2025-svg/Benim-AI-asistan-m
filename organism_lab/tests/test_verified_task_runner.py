"""No result may be labeled verified without the independent oracle."""
import json
import unittest
from organism_lab.verified_task_runner import run_job

class TaskRunnerTests(unittest.TestCase):
    def setUp(self):
        self.job={"type":"csv_mean","values":[2,4,6]}
    def test_computed_result_does_not_claim_external_verification(self):
        r=run_job(self.job)
        self.assertEqual(r["status"],"computed_unverified")
        self.assertEqual(r["result"],4.0)
        self.assertFalse(r["model_invoked"])
        self.assertEqual(len(r["task_sha256"]),64)
    def test_independent_oracle_accept_and_reject(self):
        self.assertEqual(run_job(self.job,expected=4.0)["status"],"verified")
        self.assertEqual(run_job(self.job,expected=42.0)["status"],"rejected")
    def test_optional_model_failure_never_changes_verified_result(self):
        def respond(req,timeout):
            class R:
                def __enter__(self):return self
                def __exit__(self,*args):return False
                def read(self,n=-1):return json.dumps({"response":'{"answer":12}'}).encode()
            return R()
        r=run_job(self.job,expected=4,prefer_local_model=True,transport=respond)
        self.assertEqual(r["status"],"verified")
        self.assertEqual(r["result"],4)
        self.assertEqual(r["model_status"],"rejected")
    def test_disallowed_or_unbounded_task_denied(self):
        with self.assertRaises(ValueError):run_job({"type":"run_shell","command":"whoami"})
        with self.assertRaises(ValueError):run_job({"type":"csv_mean","values":[]})
    def test_type_confusion_fails_closed(self):
        self.assertEqual(run_job(self.job,expected=True)["status"],"rejected")

if __name__=="__main__":unittest.main()
