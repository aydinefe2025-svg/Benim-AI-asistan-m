"""Adversarial validation uses actual byte-verified published CompOSE EOS #328."""
import hashlib, shutil, tempfile, pathlib, unittest, sys, numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from f87_real_tov_from_compose import EOS,SRC_MD5,SRC_SHA

SOURCE=pathlib.Path(__file__).parent/'actual'
class RealOriginalAPR(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.e=EOS(SOURCE)
 def test_unified_source_identity_bytes(self):
  b=(SOURCE/'F87_verified_publisher_original.zip').read_bytes()
  self.assertEqual(hashlib.md5(b).hexdigest(),SRC_MD5)
  self.assertEqual(hashlib.sha256(b).hexdigest(),SRC_SHA)
 def test_true_baryon_density_1833(self):
  self.assertEqual(len(self.e.nb),1833)
  self.assertGreater(self.e.nb[-1],1.3)
  self.assertLess(self.e.nb[0],1.1e-11)
  self.assertTrue(np.all(np.diff(self.e.nb)>0))
 def test_source_pressure_energy_monotone(self):
  self.assertTrue(np.all(np.diff(self.e.P)>0))
  self.assertTrue(np.all(np.diff(self.e.E)>0))
 def test_source_thermodynamic_mev_tolerance(self):
  self.assertLess(float(np.max(abs(self.e.mu_calc-self.e.mu_source))),.10)
 def test_source_causality_violation_is_never_hidden(self):
  self.assertEqual(int(np.sum(self.e.cs_source>1)),24)
  self.assertAlmostEqual(float(self.e.nb[np.flatnonzero(self.e.cs_source>1)[0]]),.8799976109400991,places=10)
 def test_no_falsified_global_causality(self):
  self.assertGreater(float(np.max(self.e.cs_source)),1.4)
 def test_real_2p073_star_central_pressure_below_native_causality_break(self):
  pc=419.1939367666721
  self.assertLess(pc,float(self.e.P[np.flatnonzero(self.e.cs_source>1)[0]]))
  star=self.e.star(pc)
  self.assertLess(abs(star['M_Msun']-2.073),1e-6)
  self.assertGreater(star['R_km'],10)
  self.assertLess(star['R_km'],11)
 def test_existing_source_modified_member_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)
   for n in ('eos.nb','eos.thermo','eos.mr','F87_verified_publisher_original.zip'):shutil.copy2(SOURCE/n,d/n)
   p=d/'eos.nb';p.write_bytes(p.read_bytes()+b'\n')
   with self.assertRaisesRegex(AssertionError,'EXTRACTED_MEMBER_MUTATED'):EOS(d)
 def test_modified_publisher_archive_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   d=pathlib.Path(tmp)
   for n in ('eos.nb','eos.thermo','eos.mr','F87_verified_publisher_original.zip'):shutil.copy2(SOURCE/n,d/n)
   p=d/'F87_verified_publisher_original.zip';b=bytearray(p.read_bytes());b[3]^=7;p.write_bytes(b)
   with self.assertRaisesRegex(AssertionError,'ZIP_HASH_MISMATCH'):EOS(d)

if __name__=='__main__':unittest.main()
