import json
import math
import unittest
from pathlib import Path

from crust_local_causal_projection import project_local_five_nodes
from thermo_consistency_local import (
    LocalThermoError,
    integrate_repaired_five_nodes,
    integrate_segment,
)

ROOT = Path(__file__).resolve().parent
FIXTURE = json.loads((ROOT / 'fixtures/j0740_source_crust_5pt_pinned.json').read_text())


class ThermodynamicReconstructionTests(unittest.TestCase):
    def test_six_source_matched_models_local_first_law(self):
        for model, source in FIXTURE['models'].items():
            with self.subTest(model=model):
                repair = project_local_five_nodes(source, cap=.95)
                result = integrate_repaired_five_nodes(source, repair['candidate_e_geom'], cap=.95)
                self.assertEqual(result['status'], 'LOCAL_PIECEWISE_LINEAR_IDENTITY_PASS')
                self.assertEqual(len(result['piecewise_cs2_over_c2']), 4)
                self.assertTrue(all(0 < c <= .95 * (1 + 1e-9) for c in result['piecewise_cs2_over_c2']))
                self.assertEqual(result['relative_baryon_density'][0], 1.0)
                self.assertTrue(all(a < b for a, b in zip(result['relative_baryon_density'], result['relative_baryon_density'][1:])))
                self.assertLess(result['max_first_law_identity_abs_error'], 1e-12)
                self.assertLess(result['max_analytic_vs_simpson_relative_error'], 1e-7)
                self.assertGreater(result['relative_difference_approx_n_vs_thermodynamic_n_at_256'], 0)

    def test_unrepaired_original_rejected(self):
        for model, rows in FIXTURE['models'].items():
            with self.subTest(model=model):
                with self.assertRaisesRegex(LocalThermoError, 'nonmonotonic'):
                    integrate_repaired_five_nodes(rows, [x['energy_geom_m_minus2'] for x in rows])

    def test_segment_constant_e_plus_p_integration(self):
        start_e, start_p = 10., 1.
        stop_e, stop_p = 12., 2.
        out = integrate_segment(start_e, start_p, stop_e, stop_p)
        expected_h = math.log((stop_e + stop_p) / (start_e + start_p)) / 3
        self.assertAlmostEqual(out['delta_h'], expected_h, places=14)
        self.assertAlmostEqual(out['delta_ln_n'], 2 * expected_h, places=14)
        self.assertLess(out['first_law_identity_abs_error'], 1e-13)

    def test_negative_energy_increment_rejected(self):
        with self.assertRaises(LocalThermoError):
            integrate_segment(10, 1, 9, 2)

    def test_noncausal_slope_rejected(self):
        with self.assertRaises(LocalThermoError):
            integrate_segment(10, 1, 10.05, 2, cap=.95)

    def test_broken_input_fails_closed(self):
        source = FIXTURE['models']['ENG']
        r = project_local_five_nodes(source, cap=.95)
        with self.assertRaises(LocalThermoError):
            integrate_repaired_five_nodes(source[:-1], r['candidate_e_geom'])
        with self.assertRaises(LocalThermoError):
            integrate_repaired_five_nodes(source, r['candidate_e_geom'][:-1])
        with self.assertRaises(LocalThermoError):
            integrate_repaired_five_nodes(source, [math.nan] + r['candidate_e_geom'][1:])


if __name__ == '__main__':
    unittest.main()
