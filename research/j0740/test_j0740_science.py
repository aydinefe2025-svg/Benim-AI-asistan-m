"""Read-only, data-free checks for the archived J0740 conditional science engine.

NOT an independent NICER/XMM photon-likelihood validation.
"""
import json
import unittest
from pathlib import Path

import numpy as np
from scipy.integrate import quad

from gravity_xpsi_v121 import native_pole_equator_gravity
from phase30_prior_core import (
    critical_radius, geometric_analytic, star_support, conditional_radius_density,
    MASS_MU, MASS_STD, R_MAX_KM,
)
from phase30_prior_corrected_eos import source_mass_pdf
from phase28_7eos_integrated_mass_radius_diagnostic import eos_curves

HERE = Path(__file__).parent


class TestNativeSourcePriorInterface(unittest.TestCase):
    def test_source_photon_sphere_shape_cutoff_is_301_not_300(self):
        radius = critical_radius(2.082)
        self.assertAlmostEqual(radius, 9.311521272839538, places=9)
        self.assertTrue(bool(star_support(2.082, radius + 0.001)))
        self.assertFalse(bool(star_support(2.082, radius - 0.001)))

    def test_joint_geometric_prior_normalization(self):
        accepted = geometric_analytic()["acceptance"]
        self.assertAlmostEqual(accepted, 0.5780634957515011, delta=1e-6)
        self.assertLess(accepted, 1.0)

    def test_radio_density_is_truncated_and_not_squared(self):
        left = MASS_MU - 5 * MASS_STD
        right = MASS_MU + 5 * MASS_STD
        total, _ = quad(source_mass_pdf, left, right, epsabs=1e-12)
        self.assertAlmostEqual(total, 1.0, places=10)
        self.assertAlmostEqual(float(source_mass_pdf(left - 0.001)), 0.0)
        self.assertAlmostEqual(float(source_mass_pdf(right + 0.001)), 0.0)

    def test_conditional_radius_prior_normalizes_on_physical_support(self):
        lower = critical_radius(2.082)
        integral, _ = quad(
            lambda r: conditional_radius_density(2.082, r),
            lower + 1e-10,
            R_MAX_KM,
            epsabs=1e-12,
        )
        self.assertAlmostEqual(integral, 1.0, places=8)
        self.assertEqual(conditional_radius_density(2.082, lower - 0.01), 0.0)

    def test_seven_source_eos_curves_loaded_without_big_archive(self):
        curves = eos_curves()
        self.assertEqual(set(curves), {
            "APR4_EPP", "ENG", "MPA1", "MS1", "MS1B", "WFF1", "WFF2",
        })
        for mass, radius in curves.values():
            self.assertGreater(len(mass), 5)
            self.assertTrue(np.all(np.diff(mass) > 0))
            self.assertTrue(np.all(np.isfinite(radius)))

    def test_pole_equator_gravity_never_equals_claim_of_full_xpsi_run(self):
        pole, equator = native_pole_equator_gravity(2.082, 12.49)
        self.assertTrue(13.7 < pole < 15)
        self.assertTrue(13.7 < equator < 15)
        self.assertGreater(pole, equator)

    def test_archived_six_density_estimators_have_explicit_nonfinal_status(self):
        with open(HERE / 'phase30_seven_eos_prior_corrected_proxy.json', encoding='utf-8') as f:
            data = json.load(f)
        self.assertIn('NOT_FINAL', data['status'])
        self.assertEqual(data['source_n'], 100000)
        self.assertEqual(len(data['grid_modes']), 6)
        for mode in data['grid_modes'].values():
            self.assertEqual(len(mode['scores']), 7)


if __name__ == '__main__':
    unittest.main()
