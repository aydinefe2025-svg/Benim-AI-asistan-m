"""F63 fail-closed fixed-J math tests; mocks NEVER scientific data."""
from __future__ import annotations
import sys,types,math,unittest
from pathlib import Path
from unittest.mock import patch
# Local standalone tests are allowed stubs; CI imports the real source conversion.
try: import jester_to_rns
except ImportError:
    stub=types.ModuleType('jester_to_rns')
    stub.from_jester_npz=lambda *a,**k: (_ for _ in ()).throw(NotImplementedError())
    stub.write_rns=lambda *a,**k: (_ for _ in ()).throw(NotImplementedError())
    sys.modules['jester_to_rns']=stub
from f63_original_mpa1_fixed_J import (patch_output_only,parse_star,fixed_j_at_density,
 turning_summary,c_call,SOURCE_SHA,F62_SHA,FREQ,DENSITY_E15)

def stub_model(ec,rr,*,J=4e48, mass=None):
    return {'ec_g_cm3':ec,'axis_ratio':rr,
            'mass_msun':2.1+1.2*(ec/1e15-1)-.5*(ec/1e15-1)**2 if mass is None else mass,
            'radius_eq_km':12,'spin_hz':340.,'J_cgs':J*(1-rr)/.025}

class F63Tests(unittest.TestCase):
    def test_exact_output_patch_only(self):
        old=r'printf("%g \t %4.3f \t %4.2f \t %4.1f \n",'
        args='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));'
        source='foo\n'+old+'\n\t '+args+'\nint physics=5;'
        out=patch_output_only(source)
        self.assertIn('star.ang_mom',out)
        self.assertIn('int physics=5;',out)
        self.assertEqual(len(source.splitlines()),len(out.splitlines()))
        self.assertNotIn(old,out)
        self.assertEqual(out.count('star.ang_mom'),1)

    def test_patch_fails_when_not_source_locked(self):
        with self.assertRaisesRegex(ValueError,'SIGNATURE_DRIFT'):
            patch_output_only('wrong source')

    def test_parser_single_genuine_C_row(self):
        row='e_c Mass Radius Spin J\n1.0153663089 2.073000000 12.533295930 346.614535604 4.01e48\n'
        a=parse_star(row,1.0153663088666426e15)
        self.assertEqual(a['mass_msun'],2.073)
        self.assertEqual(a['J_cgs'],4.01e48)

    def test_parser_rejects_wrong_mass(self):
        with self.assertRaisesRegex(ValueError,'UNPHYSICAL'):
            parse_star('1.0153663089 6.4 12.5 350 4e48\n',1.0153663088666426e15)

    def test_parser_rejects_wrong_central_density(self):
        with self.assertRaisesRegex(ValueError,'UNPHYSICAL'):
            parse_star('1.15 2.073 12.5 350 4e48\n',1.0153663088666426e15)

    def test_parser_rejects_multiple_C_rows(self):
        with self.assertRaisesRegex(ValueError,'SINGLE_FIVE_FLOAT'):
            parse_star('1.0 2.0 12 300 4e48\n1.0 2.0 12 300 4e48',1e15)

    def test_fixed_J_root_is_direct_model(self):
        calls=[]
        def probe(ec,rr):
            calls.append(rr)
            return stub_model(ec,rr)
        row=fixed_j_at_density(probe,1.1e15,4e48,seed=.97)
        self.assertLess(abs(row['relative_J_residual']),1e-5)
        self.assertAlmostEqual(row['axis_ratio'],.975,places=7)
        self.assertIn(row['axis_ratio'],calls)
        self.assertGreater(row['direct_C_evaluations'],3)

    def test_fixed_J_no_bracket_fails(self):
        with self.assertRaisesRegex(RuntimeError,'NOT_BRACKETED'):
            fixed_j_at_density(lambda e,r:{**stub_model(e,r),"J_cgs":1e48},1.1e15,4e48)

    def test_fixed_J_invalid_J_fails(self):
        with self.assertRaisesRegex(ValueError,'TARGET_J'):
            fixed_j_at_density(lambda e,r:stub_model(e,r),1e15,-4e48)

    def test_turning_diagnostic_requires_eight(self):
        q=[dict(status='DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE',ec_g_cm3=i*1e15,
                mass_msun=i,radius_eq_km=11,spin_hz=350) for i in (.8,1.2)]
        self.assertEqual(turning_summary(q)['status'],'INSUFFICIENT_DIRECT_FIXED_J_SEQUENCE')

    def test_peak_bracket_must_have_neighbors(self):
        q=[dict(status='DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE',ec_g_cm3=(.8+i*.1)*1e15,
                mass_msun=2. +.2*i-.018*i*i,radius_eq_km=11,spin_hz=350) for i in range(13)]
        res=turning_summary(q)
        self.assertEqual(res['status'],'SAMPLED_CONSTANT_J_TURNOVER_BRACKETED_NOT_GLOBAL_PROOF')
        self.assertLess(res['neighbor_masses_msun'][0],res['peak_mass_msun'])
        self.assertLess(res['neighbor_masses_msun'][2],res['peak_mass_msun'])

    def test_monotone_peak_is_not_certificate(self):
        q=[dict(status='DIRECT_C_FIXED_J_NUMERICAL_PASS_NOT_STABILITY_CERTIFICATE',ec_g_cm3=(.8+i*.1)*1e15,
                mass_msun=2.+.2*i,radius_eq_km=11,spin_hz=350) for i in range(13)]
        self.assertEqual(turning_summary(q)['status'],'UNBRACKETED_FIXED_J_MASS_PEAK')

    def test_F62_lock_and_original_physics(self):
        self.assertEqual(SOURCE_SHA,'0fab458cf5d5a63d0fafdfc3532d0a0e319fc436f732debd73d61a24c9775c22')
        self.assertEqual(F62_SHA,'aca15e711f18ef7646dc5520d8874700475def17f0bcf5e57e354cfcf3cc8f84')
        self.assertEqual(FREQ,346.536369)
        self.assertLess(max(DENSITY_E15),2.5)

if __name__=='__main__':unittest.main()