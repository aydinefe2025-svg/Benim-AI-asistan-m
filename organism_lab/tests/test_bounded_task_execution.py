"""Tests for bounded task extension, distinct from V4's fixed three tasks."""
import hashlib
import unittest
from organism_lab.bounded_task_execution import execute, gate_result

class BoundedCapabilityTests(unittest.TestCase):
    def test_csv_mean(self):
        job={"type":"csv_group_mean","csv":"grp,v\na,1.25\nb,10\na,2.75\nb,14\n","group_column":"grp","value_column":"v"}
        self.assertEqual(execute(job), {"a":"2","b":"12"})
    def test_json_pointer(self):
        self.assertEqual(execute({"type":"json_pointer","document":{"a":[{"b":12}]},"pointer":"/a/0/b"}),12)
    def test_unit_dimension(self):
        self.assertEqual(execute({"type":"convert_unit","value":"2500","from_unit":"mm","to_unit":"m"}),"2.5")
        with self.assertRaises(ValueError): execute({"type":"convert_unit","value":"20","from_unit":"kg","to_unit":"m"})
    def test_linear_fit(self):
        self.assertEqual(execute({"type":"fit_linear","points":[[1,3],[2,5],[3,7]]}),{"slope":[2,1],"intercept":[1,1]})
        with self.assertRaises(ValueError): execute({"type":"fit_linear","points":[[1,1],[1,2]]})
    def test_python_static_repair_not_execution(self):
        self.assertEqual(execute({"type":"repair_python","source":"for i in range(1, len(items)):\n    result.append(items[i])\n","bug_type":"off_by_one_range"}),"for i in range(len(items)):\n    result.append(items[i])\n")
        with self.assertRaises(ValueError): execute({"type":"repair_python","source":"import os\nos.system('whoami')\n","bug_type":"off_by_one_range"})
    def test_literal_evidence_not_semantic_claim(self):
        r=execute({"type":"verify_exact_quote","source_id":"doc1","source_text":"The experiment used 40 seeds.","quote":"40 seeds"})
        self.assertEqual(r["support_level"],"exact_quote")
        self.assertEqual(r["source_id"],"doc1")
        self.assertEqual(r["sha256"],hashlib.sha256(b"The experiment used 40 seeds.").hexdigest())
        self.assertEqual(execute({"type":"verify_exact_quote","source_id":"doc1","source_text":"The experiment used 40 seeds.","quote":"400 seeds"})["support_level"],"unverified")
    def test_fail_closed_unknown(self):
        with self.assertRaises(ValueError): execute({"type":"run_shell","command":"echo unsafe"})
    def test_gate_requires_independent_answer(self):
        self.assertEqual(gate_result(4)["status"],"unverified")
        self.assertEqual(gate_result(4,expected=5)["status"],"rejected")
        self.assertEqual(gate_result(4,expected=4)["status"],"verified")
if __name__=="__main__": unittest.main()

class VerdictTypeSafetyTests(unittest.TestCase):
    def test_numeric_values_must_never_equal_booleans(self):
        for candidate,expected in [(1,True),(True,1),(0,False),(False,0),
                                   ({"score":1},{"score":True}),([False],[0])]:
            with self.subTest(candidate=candidate,expected=expected):
                self.assertEqual(gate_result(candidate,expected=expected)["status"],"rejected")

    def test_numeric_representation_can_be_equivalent(self):
        self.assertEqual(gate_result(6,expected=6.0)["status"],"verified")
        self.assertEqual(gate_result({"score":[1,0.5]},expected={"score":[1.0,0.50]})["status"],"verified")

    def test_nonfinite_values_never_verified(self):
        self.assertEqual(gate_result(float("inf"),expected=float("inf"))["status"],"rejected")
        self.assertEqual(gate_result(float("nan"),expected=float("nan"))["status"],"rejected")
