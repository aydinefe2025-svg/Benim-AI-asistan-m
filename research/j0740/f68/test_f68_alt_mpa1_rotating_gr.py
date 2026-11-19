from pathlib import Path
import importlib.util, tempfile,unittest,hashlib,math,json
import numpy as np
P=Path(__file__).with_name('f68_alt_mpa1_rotating_gr.py')
spec=importlib.util.spec_from_file_location('f68',P);f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
PROJECT=Path(__file__).resolve().parents[1]
if PROJECT.name=='j0740':
 TABLE=PROJECT/'f67/F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat'
 ROOT=PROJECT/'f67/F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json'
 F61=PROJECT/'f61/F61_original_seven_LAL_static_TOV.json'
else:
 TABLE=Path('/mnt/data/f67/final_ci/F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat')
 ROOT=Path('/mnt/data/f67/final_ci/F67_MPA1_PCHIP_COLD_2p073_static_TOV_20261119.json')
 F61=Path('/mnt/data/f61/F61_original_seven_LAL_static_TOV.json')
class F68ScientificProvenanceTests(unittest.TestCase):
 def test_01_pinned_f67_thermo(self):self.assertEqual(f.sha(TABLE),f.F67_THERMO_SHA)
 def test_02_pinned_f67_root(self):self.assertEqual(f.sha(ROOT),f.F67_ROOT_SHA)
 def test_03_pinned_f61(self):self.assertEqual(f.sha(F61),f.F61_SHA)
 def test_04_read_f67(self):self.assertEqual(f.load_f67(TABLE,ROOT)[0].shape,(2425,4))
 def test_05_196_point_conversion(self):
  x,_=f.load_f67(TABLE,ROOT);rows,meta=f.to_rns_196(x);self.assertEqual(rows.shape,(196,4));self.assertTrue((np.diff(rows,axis=0)>0).all())
 def test_06_arbitrary_n0_flag(self):
  x,_=f.load_f67(TABLE,ROOT);_,m=f.to_rns_196(x);self.assertEqual(m['baryonic_M0_physical_calibration'],'NOT_ESTABLISHED')
 def test_07_identity(self):
  x,_=f.load_f67(TABLE,ROOT)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'ALT196.rns';f.write_rns_table(p,f.to_rns_196(x)[0]);self.assertTrue(f.verify_rns_identity(p,f.sha(p)))
 def test_08_identity_fail(self):
  x,_=f.load_f67(TABLE,ROOT)
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'ALT196.rns';f.write_rns_table(p,f.to_rns_196(x)[0]);self.assertRaisesRegex(ValueError,'NOT_BYTE_IDENTICAL',f.verify_rns_identity,p,'a'*64)
 def test_09_bad_model_sha_fail(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'F67.dat';p.write_text('123\n');self.assertRaisesRegex(ValueError,'SHA_DRIFT',f.load_f67,p,ROOT)
 def test_10_bad_tov_sha_fail(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'F67.json';p.write_text('{}\n');self.assertRaisesRegex(ValueError,'SHA_DRIFT',f.load_f67,TABLE,p)
 def test_11_old_source_not_new_model(self):
  src=f.load_f61(F61);self.assertEqual(set(f'{x:.3f}' for x in f.TARGETS),set(src).intersection({f'{x:.3f}' for x in f.TARGETS}))
 def test_12_seeds_in_range(self):
  x,_=f.load_f67(TABLE,ROOT);src=f.load_f61(F61)
  for m in f.TARGETS:self.assertTrue(2e14<f.seed_for_mass(x,src,m)<4e15)
 def test_13_no_false_spin_pass(self):
  star={'mass_msun':2.073,'radius_eq_km':12.4,'spin_hz_reported':345.5,'central_energy_density_g_cm3':1e15}
  self.assertRaisesRegex(ValueError,'MASS_OR_FREQUENCY',f.physical_output_gate,star,2.073,f.TARGET_SPIN)
 def test_14_genuine_spin_pass(self):
  star={'mass_msun':2.073,'radius_eq_km':12.4,'spin_hz_reported':f.TARGET_SPIN,'central_energy_density_g_cm3':1e15}
  self.assertIsNone(f.physical_output_gate(star,2.073,f.TARGET_SPIN))
 def test_15_no_physical_n0(self):self.assertIn('NOT_ORIGINAL',f.MODEL)
 def test_16_static_G_RNS_roundtrip(self):
  x,_=f.load_f67(TABLE,ROOT);rows,m=f.to_rns_196(x);self.assertTrue(rows[0,0]>0);self.assertTrue(rows[-1,0]>2e15)
 def test_17_file_name_pin(self):
  with tempfile.TemporaryDirectory() as td:self.assertRaisesRegex(ValueError,'BASENAME_PIN',f.write_rns_table,Path(td)/'old_MPA1.rns',np.ones((196,4)))
 def test_18_source_index_matches_mass(self):
  obj=json.loads(ROOT.read_text());self.assertLess(abs(obj['new_M2p073_PCHIP_root']['M_msun']-2.073),1e-5)
if __name__=='__main__':unittest.main()