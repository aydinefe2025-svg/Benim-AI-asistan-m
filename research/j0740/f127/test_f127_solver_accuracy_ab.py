import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f127_solver_accuracy_ab import patch_findmodel,instrument_equil,parse_native,check_f124,patch_mesh,sha
SRC=Path(os.environ['F124_ARTIFACT_ZIP'])
EOS=Path(os.environ['F99_EOS_PATH'])
class SourcePatchTests(unittest.TestCase):
 def test_real_f124_root_pin(self):
  s=check_f124(SRC.read_bytes(),EOS.read_bytes())
  self.assertLess(s['J_relative_error'],1e-9)
 def test_source_tamper_reject(self):
  with self.assertRaisesRegex(ValueError,'F124_ZIP_SHA_MISMATCH'):check_f124(SRC.read_bytes()+b'x',EOS.read_bytes())
 def test_eos_tamper_reject(self):
  with self.assertRaisesRegex(ValueError,'F99_EOS_SHA_MISMATCH'):check_f124(SRC.read_bytes(),EOS.read_bytes()+b'x')
 def test_initialize_exactly_once_and_tight_only_when_requested(self):
  s='int rns(double r_ratio,\n ...\n  int a_check;\n  double accuracy=1e-4;'
  a=patch_findmodel(s,False);b=patch_findmodel(s,True)
  self.assertIn('int a_check=0;',a)
  self.assertIn('accuracy=1e-4;',a)
  self.assertIn('accuracy=1e-7;',b)
  self.assertNotIn('accuracy=1e-4;',b)
 def test_source_shape_drift_reject(self):
  with self.assertRaisesRegex(ValueError,'UNEXPECTED_PINNED_RNS_SOURCE'):patch_findmodel('int rns(double r_ratio,\nint a_check=0;',False)
 def test_exact_equilibrium_diagnostic_patch(self):
  s='void spin(){\n }   /* end while */\n}'
  p=instrument_equil(s)
  self.assertIn('F127_SPIN_FINAL_DIFFERENCE',p)
  self.assertIn('ITERATIONS %d ACCURACY %.17e ACHECK %d',p)
  self.assertLess(p.index('/* end while */'),p.index('F127_SPIN_FINAL_DIFFERENCE'))
 def test_native_diagnostic_parser(self):
  stdout='e_c mass radius spin J\n2.622286765625e+00 2.184227160747 10.14016291537 345.4072767354 4.824562679575e+48\n'
  stderr=('F127_SPIN_FINAL_DIFFERENCE 9.00000000000000000e-05 ITERATIONS 5 ACCURACY 1.00000000000000000e-04 ACHECK 0\n'
         'F127_SPIN_FINAL_DIFFERENCE 5.00000000000000000e-08 ITERATIONS 7 ACCURACY 1.00000000000000000e-07 ACHECK 0')
  r=parse_native(stdout,stderr)
  self.assertEqual(r['spin_iterations'],7);self.assertEqual(r['a_check'],0)
  self.assertEqual(r['spin_call_count'],2);self.assertEqual(len(r['spin_call_diagnostics']),2)
  self.assertLess(r['spin_last_radius_relative_change'],r['spin_accuracy_requested'])
 def test_nonconverged_rns_rejected(self):
  stdout='2.622286765625e+00 2.184227160747 10.14016291537 345.4072767354 4.824562679575e+48'
  stderr='F127_SPIN_FINAL_DIFFERENCE 1.0e-3 ITERATIONS 7 ACCURACY 1e-4 ACHECK 0'
  with self.assertRaisesRegex(ValueError,'RNS_INNER_SPIN_DIVERGED_OR_NOT_CONVERGED'):parse_native(stdout,stderr)
 def test_mesh_patch_fail_closed(self):
  m=patch_mesh('HIGHSIZE=-DMDIV=151 -DSDIV=301')
  self.assertIn('MDIV=3001',m)
  with self.assertRaises(ValueError):patch_mesh(m)
if __name__=='__main__':unittest.main(verbosity=2)
