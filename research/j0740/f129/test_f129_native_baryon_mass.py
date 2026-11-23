import hashlib
import io
import json
import pathlib
import os
import tempfile
import unittest
import zipfile

from f129_native_baryon_mass import patch_native_mass0, parse_baryon_star, load_ultra_reference, summarize_pair

ORIGINAL_RNS = '''printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",\n\t      star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));'''

class NativeBaryonMassTests(unittest.TestCase):
    def test_01_print_patch_adds_baryonic_mass_as_sixth_field(self):
        result = patch_native_mass0(ORIGINAL_RNS)
        self.assertIn('star.Mass_0/MSUN', result)
        self.assertIn('star.ang_mom', result)
        self.assertEqual(result.count('%.12e'), 6)
        self.assertEqual(result.count('star.Mass_0/MSUN'), 1)

    def test_02_print_patch_rejects_unpinned_change_and_duplicate(self):
        with self.assertRaisesRegex(ValueError, 'RNS_PRINT_SOURCE_DRIFT'):
            patch_native_mass0('wrong source')
        with self.assertRaisesRegex(ValueError, 'RNS_PRINT_SOURCE_DRIFT'):
            patch_native_mass0(ORIGINAL_RNS + ORIGINAL_RNS)

    def test_03_baryon_star_parser_accepts_real_shape_and_J(self):
        line = '2.622286757812e+00 2.185057237229e+00 1.014186190306e+01 3.452806563388e+02 4.824562679615e+48 2.53e+00\n'
        err = 'F127_SPIN_FINAL_DIFFERENCE 1.2e-10 ITERATIONS 48 ACCURACY 1e-09 ACHECK 0\n'
        star = parse_baryon_star(line, err, 2622286757812500, 0.990157633695)
        self.assertAlmostEqual(star['M_baryonic_msun'], 2.53)
        self.assertLess(star['J_relative_error'], 1e-9)
        self.assertLess(star['last_spin_diff'], 1e-9)

    def test_04_parser_rejects_missing_M0_and_divergence(self):
        err = 'F127_SPIN_FINAL_DIFFERENCE 1.2e-10 ITERATIONS 48 ACCURACY 1e-09 ACHECK 0\n'
        with self.assertRaises(ValueError):
            parse_baryon_star('2.622286757812e0 2.185 10.141 345.28 4.824562679575e48\n', err, 2622286757812500, .990157633695)
        with self.assertRaises(ValueError):
            parse_baryon_star('2.622286757812e0 2.185 10.141 345.28 4.824562679575e48 2.53\n', err.replace('1.2e-10','1.2e-08'), 2622286757812500,.990157633695)

    def test_05_pinned_reference_rejects_tampering(self):
        src = pathlib.Path(os.environ.get('F129_ULTRA_ZIP', '/mnt/data/F128_ULTRATIGHT_SOURCE_20261123.zip'))
        self.assertTrue(src.exists())
        result = load_ultra_reference(src)
        self.assertEqual(len(result), 2)
        self.assertEqual(result['low']['rho_g_cm3'], 2622286757812500)
        self.assertEqual(result['high']['rho_g_cm3'], 2622286761718750)
        with tempfile.TemporaryDirectory() as tmp:
            altered = pathlib.Path(tmp)/'bad.zip'
            altered.write_bytes(src.read_bytes() + b'attack')
            with self.assertRaises(ValueError):load_ultra_reference(altered)

    def test_06_pair_compare_rejects_mismatch_and_computes_delta(self):
        a={'M_msun':2.185057237229,'M_baryonic_msun':2.51, 'J_relative_error':1e-11}
        b={'M_msun':2.185057237274,'M_baryonic_msun':2.5100000001,'J_relative_error':2e-11}
        result=summarize_pair(a,b)
        self.assertAlmostEqual(result['delta_M_baryonic_msun'],1e-10,delta=1e-13)
        self.assertGreater(result['delta_M_gravitational_msun'],0)
        with self.assertRaises(ValueError):summarize_pair({**a,'J_relative_error':1e-4},b)

if __name__=='__main__': unittest.main()