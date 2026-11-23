import unittest,sys,io,json,zipfile,hashlib,os,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from f131_field_residual import (instrument_field_residual,parse_metric_probe,
                                 pin_f129_reference,compare_to_F129,parse_f131_output)

class SourceMetricProbeTests(unittest.TestCase):
 def test_01_source_patch_is_output_only_and_has_three_metric_residuals(self):
  src='''void spin(){\n    f2n = dmatrix(1,LMAX+1,1,SDIV);\n  while(dif> accuracy || n_of_it<2) { \n            rho[s][m]=rsm + cf*(sum_rho-rsm);\n            gama[s][m]=gsm + cf*(sum_gama-gsm);\n            omega[s][m]=omsm + cf*(sum_omega-omsm);\n }   /* end while */\n   fprintf(stderr,"F127_SPIN_FINAL_DIFFERENCE %.17e ITERATIONS %d ACCURACY %.17e ACHECK %d\\n",dif,n_of_it,accuracy,a_check);\n}'''
  patched=instrument_field_residual(src)
  self.assertIn('F131_FIELD_FINAL',patched)
  self.assertIn('fabs(sum_rho-rsm)',patched)
  self.assertIn('fabs(sum_gama-gsm)',patched)
  self.assertIn('fabs(sum_omega-omsm)',patched)
  self.assertEqual(patched.count('rho[s][m]=rsm + cf*(sum_rho-rsm);'),1)
  self.assertEqual(patched.count('gama[s][m]=gsm + cf*(sum_gama-gsm);'),1)
  self.assertEqual(patched.count('omega[s][m]=omsm + cf*(sum_omega-omsm);'),1)
 def test_02_source_drift_rejected(self):
  with self.assertRaisesRegex(ValueError,'SOURCE_DRIFT'):instrument_field_residual('void unrelated() {}')
 def test_03_metric_parser_accepts_two_spins_and_checks_final(self):
  t=('F131_FIELD_FINAL 1e-3 1e-4 1e-5 1.0 2.0 3.0 ITERATIONS 6 ACHECK 0\n'
     'F131_FIELD_FINAL 3e-8 4e-8 5e-8 0.7 0.9 0.03 ITERATIONS 48 ACHECK 0')
  r=parse_metric_probe(t)
  self.assertEqual(len(r['spin_calls']),2);self.assertEqual(r['last']['iterations'],48)
  self.assertAlmostEqual(r['last']['rel_delta_rho'],3e-8/0.7)
  self.assertAlmostEqual(r['last']['rel_delta_omega'],5e-8/0.03)
  initial=('F131_FIELD_FINAL 1e-8 2e-8 0 2 1 0 ITERATIONS 32 ACHECK 0\\n'
           'F131_FIELD_FINAL 3e-8 4e-8 5e-8 0.7 0.9 0.03 ITERATIONS 48 ACHECK 0')
  z=parse_metric_probe(initial)
  self.assertIsNone(z['spin_calls'][0]['rel_delta_omega'])
  self.assertAlmostEqual(z['largest_global_field_relative_update'],5e-8/0.03)
 def test_04_metric_probe_refuses_missing_unsafe_or_nonfinite(self):
  for x in ['', 'F131_FIELD_FINAL nan 0 0 1 1 1 ITERATIONS 48 ACHECK 0',
            'F131_FIELD_FINAL -1 0 0 1 1 1 ITERATIONS 48 ACHECK 0',
            'F131_FIELD_FINAL 1 0 0 1 1 1 ITERATIONS 48 ACHECK 200',
            'F131_FIELD_FINAL 1e-8 2e-8 0 2 1 0 ITERATIONS 32 ACHECK 0\\nF131_FIELD_FINAL 1e-8 2e-8 0 2 1 0 ITERATIONS 48 ACHECK 0']:
   with self.subTest(x=x):
    with self.assertRaises(ValueError):parse_metric_probe(x)
 def test_05_original_F129_SHA_and_native_star_pinned(self):
  path=Path(os.environ['F131_ORIGINAL_F129_ZIP'])
  refs=pin_f129_reference(path.read_bytes())
  self.assertEqual(set(refs),{'low','high'})
  self.assertEqual(refs['low']['rho_g_cm3'],2622286757812500)
  with self.assertRaisesRegex(ValueError,'F129_ARTIFACT_SHA'):pin_f129_reference(path.read_bytes()+b'tamper')
 def test_06_output_pair_must_agree_with_actual_F129_native_C_star(self):
  refs=pin_f129_reference(Path(os.environ['F131_ORIGINAL_F129_ZIP']).read_bytes())
  for label in ('low','high'):
   star=refs[label]
   f=f'{star["rho_g_cm3"]/1e15:.12e} {star["M_msun"]:.12e} {star["R_eq_km"]:.12e} {star["f_hz"]:.12e} {star["J_cgs"]:.12e} {star["M_baryonic_msun"]:.12e}'
   stderr=('F127_SPIN_FINAL_DIFFERENCE 1e-10 ITERATIONS 32 ACCURACY 1e-9 ACHECK 0\n'
           'F131_FIELD_FINAL 1e-6 1e-7 1e-8 1 1 1 ITERATIONS 32 ACHECK 0\n'
           'F127_SPIN_FINAL_DIFFERENCE 1e-10 ITERATIONS 48 ACCURACY 1e-9 ACHECK 0\n'
           'F131_FIELD_FINAL 1e-6 1e-7 1e-8 1 1 1 ITERATIONS 48 ACHECK 0')
   got=parse_f131_output(f,stderr,star['rho_g_cm3'])
   compare_to_F129(got,star)
   with self.assertRaisesRegex(ValueError,'WITNESS_CHANGE'):compare_to_F129({**got,'M_msun':got['M_msun']+1e-5},star)
 def test_07_native_parser_rejects_missing_field(self):
  with self.assertRaises(ValueError):parse_f131_output('2.6 2.18 10.1 345 4.8e48 2.6','F127_SPIN_FINAL_DIFFERENCE 1e-10 ITERATIONS 48 ACCURACY 1e-9 ACHECK 0',2622286757812500)

if __name__=='__main__':unittest.main(verbosity=2)
