import pathlib
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import native_six_direct_rns as a

class NativeSixSourceTests(unittest.TestCase):
    def test_six_are_only_missing_models(self):
        self.assertEqual(set(a.NAMES),{'APR4_EPP','ENG','MS1','MS1B','WFF1','WFF2'})
        self.assertNotIn('MPA1',a.NAMES)
    def test_separate_exact_pinned_sha_per_original_model(self):
        self.assertEqual(set(a.SOURCE_SHA),set(a.NAMES))
        self.assertEqual(len(set(a.SOURCE_SHA.values())),6)
        self.assertTrue(all(len(x)==64 for x in a.SOURCE_SHA.values()))
    def test_only_original_f61_reference_accepted(self):
        with self.assertRaises(ValueError):
            a.assert_npz_and_F61(pathlib.Path('missing.npz'),pathlib.Path('missing.json'),'MPA1')
    def test_no_fabricated_direct_stars_on_source_failure(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            d=pathlib.Path(td)
            b=d/'binary';b.write_bytes(b'not actual solver')
            r=a.run_one(d/'missing',d/'missing-f61',b,'ENG',d/'out')
            self.assertEqual(r['status'],'FAILED_DIRECT_PHYSICS_NUMERICAL_GUARD_NOT_CLAIMED')
            self.assertNotIn('196',r['meshes'])
    def test_mass_spin_and_mesh_gates_are_narrow(self):
        self.assertLessEqual(a.STATIC_DIFF_LIMIT_KM,.20)
        self.assertLessEqual(a.MESH_DIFF_LIMIT_KM,.060)
        self.assertEqual(a.TABLES,(151,196))
        self.assertAlmostEqual(a.TARGET,2.073,places=9)
    def test_eos_is_not_silently_renamed_or_accepted(self):
        import inspect
        code=inspect.getsource(a.run_one)
        self.assertIn('physical_certification',code)
        self.assertIn('NOT_ESTABLISHED',code)
        self.assertIn('original_EOS_edited',code)
        self.assertIn('False',code)
        self.assertIn('trial_root(',code)

if __name__=='__main__': unittest.main()
