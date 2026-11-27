"""Regression for 26 Nov actual six task families (same wire format, no label echoes)."""
import unittest
from organism_lab.bounded_task_execution import execute

class LegacyBridgeTests(unittest.TestCase):
    def test_csv_mean(self):
        self.assertEqual(execute({"type":"csv_mean","values":[-5,2,7]}),4/3)
    def test_json_lookup(self):
        self.assertEqual(execute({"type":"json_nested_lookup","data":{"analysis":{"period":{"4":9}}},"path":["analysis","period","4"]}),9)
    def test_unit(self):
        self.assertEqual(execute({"type":"unit_conversion","amount":6.25,"from":"kg","to":"g"}),6250.0)
    def test_slope(self):
        self.assertEqual(execute({"type":"linear_fit_slope","points":[[-2,1],[-1,4],[0,7],[1,10]]}),3.0)
    def test_patch_does_not_echo_ground_truth(self):
        job={"type":"python_bug_fix","source":"def add(a,b):\n    return a-b\n","test":"add(4,6)==10","expected_patch":"DO NOT TRUST THIS UNVERIFIED LABEL"}
        self.assertEqual(execute(job),"return a+b")
    def test_source_claim_flag_does_not_invent_peer_review(self):
        self.assertTrue(execute({"type":"source_citation_check","claim":"N=12","sources":[{"id":"s1","text":"Results N=12 here","peer_reviewed":True}],"must_peer_review":True}))
        self.assertFalse(execute({"type":"source_citation_check","claim":"N=12","sources":[{"id":"s1","text":"Results N=12 here","peer_reviewed":False}],"must_peer_review":True}))
    def test_bad_legacy_data_rejected(self):
        for job in [{"type":"csv_mean","values":[1,True]},{"type":"json_nested_lookup","path":["a"]},
                    {"type":"python_bug_fix","source":"import os\n", "test":"add(2,3)==5"},
                    {"type":"source_citation_check","claim":"x","sources":[],"must_peer_review":True}]:
            with self.subTest(job=job),self.assertRaises(ValueError): execute(job)
if __name__=="__main__": unittest.main()
