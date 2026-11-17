"""Acceptance: tabular LALSuite derivative must discriminate from analytic SLy at join."""
import os,unittest
from pathlib import Path
from audit_apr4_native_tabular_transition_20261117 import compare,SOURCE_SHA,sha256

SOURCE=Path(os.environ.get("JESTER_APR4_SOURCE","jester-source/jesterTOV/tabulated_eos/lalsuite/APR4_EPP.npz"))
class TestNamedAPR4TabularVsAnalytic(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.source=SOURCE.resolve()
  cls.d=compare(cls.source)
 def test_locked_source(self):
  self.assertEqual(sha256(self.source),SOURCE_SHA)
  self.assertEqual(self.d["input"]["n_source_rows"],865)
 def test_real_native_query_is_finite(self):
  self.assertTrue(self.d["checks"]["native_rows_finite"])
 def test_transition_is_in_gamma_jump(self):
  self.assertTrue(self.d["checks"]["source_transition_gamma_in_analytic_bracket"])
 def test_tabular_native_beats_analytic_reference_at_transition(self):
  self.assertTrue(self.d["checks"]["native_closer_than_analytic_at_row262"])
if __name__=="__main__": unittest.main()
