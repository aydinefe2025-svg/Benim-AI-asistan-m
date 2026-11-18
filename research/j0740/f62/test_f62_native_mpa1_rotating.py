"""Fail-closed F62 scientific unit tests. Simulator stubs are *only tests*, never evidence."""
import json
import math
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

# In CI use real project modules; local standalone unit tests may use API stubs.
try:
    import jester_to_rns
    import rns_benchmark
    import axis_ratio_rns
except ImportError:
    jester_to_rns=types.ModuleType('jester_to_rns')
    jester_to_rns.C=299792458.0;jester_to_rns.G=6.67430e-11
    jester_to_rns.from_jester_npz=lambda *a,**k: (_ for _ in ()).throw(NotImplementedError())
    jester_to_rns.write_rns=lambda *a,**k: (_ for _ in ()).throw(NotImplementedError())
    rns_benchmark=types.ModuleType('rns_benchmark')
    rns_benchmark.OBSERVED_SPIN_HZ=346.536369
    rns_benchmark.run_rns=lambda *a,**k: (_ for _ in ()).throw(NotImplementedError())
    rns_benchmark.sha256_file=lambda p:'00'*32
    axis_ratio_rns=types.ModuleType('axis_ratio_rns')
    axis_ratio_rns.run_rns_at_spin_with_ratio_fallback=lambda *a,**k: (_ for _ in ()).throw(NotImplementedError())
    sys.modules.update({'jester_to_rns':jester_to_rns,'rns_benchmark':rns_benchmark,'axis_ratio_rns':axis_ratio_rns})
from f62_rns_precision_patch import precision_patch,OLD,NEW
from f62_native_mpa1_rotating import (gate_star,trial_root,compare_results,rho_from_F61_static,
                                     load_sources,OBSERVED_SPIN_HZ,GRID_POINTS,TARGETS,F61_REPORT_SHA,
                                     MESH_RADIUS_TOL_KM)
import f62_native_mpa1_rotating as f62
import numpy as np


def model(m=2.073,r=12.5,f=346.536369,rho=1e15):
    return dict(mass_msun=m,radius_eq_km=r,spin_hz_reported=f,central_energy_density_g_cm3=rho)


class F62Tests(unittest.TestCase):
    def test_C_print_precision_only_patch_is_unique(self):
        original='before\n    '+OLD+'\n equations unchanged\n'
        updated=precision_patch(original)
        self.assertIn(NEW,updated)
        self.assertNotIn(OLD,updated)
        self.assertIn('equations unchanged',updated)
        self.assertEqual(len(updated.splitlines()),len(original.splitlines()))

    def test_reject_unexpected_upstream_RNS_source(self):
        with self.assertRaisesRegex(ValueError,'PRINTF_SIGNATURE_DRIFT'):
            precision_patch('some different upstream C source')

    def test_physics_identity_unmodified(self):
        self.assertEqual(GRID_POINTS,(151,196))
        self.assertEqual(TARGETS,(2.073,2.175,2.2,2.25))
        self.assertEqual(f62.MPA1_NPZ_SHA,'0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22')

    def test_accept_real_root_with_physical_numeric_limits(self):
        self.assertTrue(gate_star(model(),2.073,OBSERVED_SPIN_HZ))

    def test_reject_wrong_star_mass(self):
        with self.assertRaisesRegex(ValueError,'ROOT_RESIDUAL_FAIL'):
            gate_star(model(m=2.08),2.073,OBSERVED_SPIN_HZ)

    def test_reject_wrong_star_spin(self):
        with self.assertRaisesRegex(ValueError,'ROOT_RESIDUAL_FAIL'):
            gate_star(model(f=345.9),2.073,OBSERVED_SPIN_HZ)

    def test_reject_unphysical_radius(self):
        with self.assertRaisesRegex(ValueError,'NUMERICAL_BOUNDS'):
            gate_star(model(r=5.),2.073,OBSERVED_SPIN_HZ)

    def test_reject_nonfinite_model(self):
        with self.assertRaisesRegex(ValueError,'NUMERICAL_BOUNDS'):
            gate_star(model(m=float('nan')),2.073,OBSERVED_SPIN_HZ)

    def test_source_bad_crust_is_not_silenced_by_input(self):
        # Any incorrect source NPZ must fail SHA before a stellar solution.
        with self.assertRaisesRegex(ValueError,'SOURCE_SHA_DRIFT'):
            load_sources(Path(__file__),Path(__file__))

    def test_F61_static_provenance(self):
        import hashlib
        testfile=Path(__file__)
        self.assertNotEqual(hashlib.sha256(testfile.read_bytes()).hexdigest(),F61_REPORT_SHA)
        self.assertAlmostEqual(f62.C2G,f62.C*f62.C/f62.G*1e-3)

    def test_direct_C_root_proof_never_returns_interpolated_star(self):
        calls=[]
        def physical_solver(binary,table,*,central_density,spin_hz,**kw):
            calls.append(float(central_density))
            m=1.2+.9*(central_density/1e15)
            return model(m=m,r=11.4+central_density/1e16,f=spin_hz,rho=central_density)
        with patch.object(f62,'run_rns_at_spin_with_ratio_fallback',side_effect=physical_solver):
            res=trial_root(Path('test_rns'),Path('eos'),2.073,1e15,OBSERVED_SPIN_HZ)
        self.assertEqual(res['status'],'PASS_DIRECT_RNS_C_MASS_FREQUENCY_ROOT_NUMERICAL_ONLY')
        self.assertAlmostEqual(res['star']['mass_msun'],2.073,places=6)
        self.assertIn(res['star']['central_energy_density_g_cm3'],calls)
        self.assertGreater(res['actual_direct_C_calls'],5)

    def test_fail_closed_no_direct_C_mass_bracket(self):
        def no_bracket(binary,table,*,central_density,spin_hz,**kw):
            return model(m=1.7,r=12.3,f=spin_hz,rho=central_density)
        with patch.object(f62,'run_rns_at_spin_with_ratio_fallback',side_effect=no_bracket):
            with self.assertRaisesRegex(RuntimeError,'NO_DIRECT_RNS_BRACKET'):
                trial_root(Path('test_rns'),Path('eos'),2.073,1e15,OBSERVED_SPIN_HZ)

    def test_static_root_uses_zero_frequency(self):
        calls=[]
        def solver(binary,table,*,central_density,spin_hz,**kw):
            calls.append(spin_hz)
            return model(m=1.2+.9*central_density/1e15,r=12.4,f=0,rho=central_density)
        with patch.object(f62,'run_rns',side_effect=solver):
            r=trial_root(Path('rns'),Path('eos'),2.073,1e15,0.)
        self.assertTrue(all(x==0. for x in calls))
        self.assertEqual(r['star']['spin_hz_reported'],0.)

    def test_reject_mislabeled_single_mesh(self):
        with self.assertRaisesRegex(ValueError,'INVALID_MESH_SET'):
            compare_results({'196':{}},{})

    def test_compare_real_results_mesh(self):
        def row(m,target,static_r,rot_r):
            return {'rotating':{'star':model(m,rot_r,OBSERVED_SPIN_HZ)},
                    'static':{'star':model(m,static_r,0.)}}
        d={'151':{'targets':{}},'196':{'targets':{}}};refs={}
        for mass in TARGETS:
            k=f'{mass:.3f}'
            d['151']['targets'][k]=row(mass,mass,12.00,12.50)
            d['196']['targets'][k]=row(mass,mass,12.00,12.51)
            refs[k]={'radius_km':12.00}
        c=compare_results(d,refs)
        self.assertEqual(len(c),4)
        self.assertAlmostEqual(c['2.250']['RNS_196pt_minus_151pt_eq_radius_km'],.01)
        self.assertIn('FAIL_ORIGINAL',c['2.073']['source_original_EOS_global_physical_certification'])

    def test_reject_mesh_radii_divergence(self):
        self.assertGreater(MESH_RADIUS_TOL_KM,0)
        def row(m,r):return {'rotating':{'star':model(m,r,OBSERVED_SPIN_HZ)},'static':{'star':model(m,12,0)}}
        d={str(n):{'targets':{f'{m:.3f}':row(m,12.5+(.20 if n==196 else 0)) for m in TARGETS}}
           for n in GRID_POINTS}
        ref={f'{m:.3f}':{'radius_km':12} for m in TARGETS}
        with self.assertRaisesRegex(ValueError,'GRID_NOT_CONVERGED'):
            compare_results(d,ref)

    def test_reject_static_LAL_disagreement(self):
        def row(m):return {'rotating':{'star':model(m,12.5,OBSERVED_SPIN_HZ)},'static':{'star':model(m,12,0)}}
        d={str(n):{'targets':{f'{m:.3f}':row(m) for m in TARGETS}} for n in GRID_POINTS}
        ref={f'{m:.3f}':{'radius_km':11} for m in TARGETS}
        with self.assertRaisesRegex(ValueError,'LAL_TOV_AND_RNS_STATIC_DISAGREE'):
            compare_results(d,ref)

if __name__=='__main__':unittest.main()