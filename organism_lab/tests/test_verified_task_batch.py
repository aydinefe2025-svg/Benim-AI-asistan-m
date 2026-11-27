import unittest
from organism_lab.verified_task_batch import run_batch

class BatchTests(unittest.TestCase):
    def test_replay_is_deduplicated_and_fails_closed(self):
        good={"type":"csv_mean","values":[1,2,3]}
        second={"type":"json_nested_lookup","data":{"a":{"b":5}},"path":["a","b"]}
        malicious={"type":"run_shell","command":"whoami"}
        report=run_batch([good,good,second,malicious])
        self.assertEqual(report["total"],4)
        self.assertEqual(report["executed"],2)
        self.assertEqual(report["duplicates"],1)
        self.assertEqual(report["rejected"],1)
        self.assertEqual([x["status"] for x in report["results"]],
                         ["computed_unverified","duplicate","computed_unverified","rejected"])
        self.assertEqual(report["results"][2]["result"],5)
        self.assertTrue(all(item["status"]!="verified" for item in report["results"]))

    def test_budget_is_finite(self):
        with self.assertRaises(ValueError):
            run_batch([{"type":"csv_mean","values":[1]}]*33)
        with self.assertRaises(ValueError):
            run_batch([])
    def test_fresh_batches_do_not_share_hidden_state(self):
        job={"type":"csv_mean","values":[1,3]}
        self.assertEqual(run_batch([job])["executed"],1)
        self.assertEqual(run_batch([job])["executed"],1)

if __name__=="__main__":unittest.main()
