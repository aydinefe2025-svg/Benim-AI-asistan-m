import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import f81_exact_mass_spin as F

class F81ExactMassSpinTests(unittest.TestCase):
    def test_two_constraint_roots_correct_reported_mass_and_spin(self):
        calls=[]
        def simulate(logrho,requested_f):
            calls.append((logrho,requested_f))
            rho=10.0**logrho
            return {'M_msun':2.073+1.7*(logrho-15.01)+0.0001*(requested_f-346.5),
                'spin_hz':requested_f+0.081+0.001*(logrho-15.01),
                'R_equatorial_km':12.52+0.1*(logrho-15.01),
                'J_cgs':6.1e48,'rho_c_g_cm3':rho}
        result=F.solve_grid(simulate,seed_rho=1.023e15, target_m=2.073, target_f=346.536369)
        self.assertLess(abs(result['M_msun']-2.073),1e-6)
        self.assertLess(abs(result['spin_hz']-346.536369),.005)
        self.assertLess(abs(result['commanded_f_hz']-346.455369),.004)
        self.assertGreater(len(calls),4)
        self.assertGreater(result['J_cgs'],0)

    def test_constant_spin_ignoring_command_cannot_pass(self):
        def bad(logrho,requested_f):
            return {'M_msun':2.073+1.7*(logrho-15.01), 'spin_hz':346.65,
                'R_equatorial_km':12.5,'J_cgs':6e48, 'rho_c_g_cm3':10**logrho}
        with self.assertRaisesRegex(ValueError,'SPIN_NOT_BRACKETED'):
            F.solve_grid(bad,1.023e15,2.073,346.536369)

    def test_mass_unbracketed_refuses_to_make_star(self):
        def too_light(logrho,requested_f):
            return {'M_msun':1.2, 'spin_hz':requested_f,
                'R_equatorial_km':12.5,'J_cgs':6e48, 'rho_c_g_cm3':10**logrho}
        with self.assertRaisesRegex(ValueError,'MASS_NOT_BRACKETED'):
            F.solve_grid(too_light,1.023e15,2.073,346.536369)

    def test_source_stdout_must_contain_real_J(self):
        p=F.parse_rns('header\n1.023e+00 2.073e+00 1.252e+01 3.465e+02 6.100e+48\n')
        self.assertEqual(p['J_cgs'],6.1e48)
        with self.assertRaisesRegex(ValueError,'FIVE_C_COLUMNS'):
            F.parse_rns('1.023e+00 2.073e+00 1.252e+01 3.465e+02\n')

    def test_patch_exact_print_only_no_equations(self):
        s='    printf("%g \\t %4.3f \\t %4.2f \\t %4.1f \\n",\n\t star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));\n'
        p=F.patch_print_only(s)
        self.assertEqual(p.count('star.ang_mom'),1)
        self.assertIn('%.12e',p)
        self.assertNotIn('%4.3f',p)
        with self.assertRaisesRegex(ValueError,'RNS_SOURCE_PRINT_DRIFT'):
            F.patch_print_only('missing')

    def test_reject_nonfinite_C_output(self):
        for x in ['nan','inf']:
            with self.assertRaises(ValueError):
                F.parse_rns(f'1.023e+00 2.073e+00 1.25e+01 346.5 {x}\n')

    def test_no_physical_model_promotion(self):
        self.assertEqual(F.PHYSICAL_EOS_ACCEPTANCE,'NOT_ESTABLISHED')
        self.assertEqual(F.SOURCE_XPSI,'NOT_RUN')

class F81AcceptanceTests(unittest.TestCase):
    def sample(self):
        def star(f=F.TARGET_F, m=F.TARGET_M):
            return {'status':'ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY',
                    'M_msun':m,'spin_hz':f,'commanded_f_hz':f-0.08,
                    'J_cgs':6e48,'R_equatorial_km':12.52,
                    'rho_c_g_cm3':1.02e15,'direct_C_evaluations':12}
        tov={'model':F.TOV_MODEL,
             'status':'PASS_NUMERICAL_HYBRID_EOS_CANDIDATE_PHYSICAL_ACCEPTANCE_NOT_ESTABLISHED',
             'TOV':{'M2p073':{'R_km':12.399789130135465}}}
        return {g:star() for g in F.GRIDS},tov,{g:'a'*64 if i==0 else 'b'*64 for i,g in enumerate(F.GRIDS)}

    def test_both_actual_stars_are_reported_numerical_not_physical(self):
        s,tov,b=self.sample()
        ans=F.audit_pair(s,tov,F.EOS_SHA,b)
        self.assertEqual(ans['status'],'TWO_GRID_REAL_C_MASS_SPIN_J_NUMERICAL_PASS_NOT_PHYSICAL_EOS')
        self.assertEqual(ans['source_native_XPSI_photon_likelihood'],'NOT_RUN')
        self.assertEqual(ans['global_fixed_J_stability'],'NOT_RUN')
        self.assertGreater(ans['grids']['151x301']['I_derived_cgs'],0)

    def test_detects_second_grid_spin_mismatch(self):
        s,tov,b=self.sample();s['201x401']['spin_hz']+=0.02
        with self.assertRaisesRegex(ValueError,'MEASURED_MASS_SPIN_J_NOT_ACCEPTED'):
            F.audit_pair(s,tov,F.EOS_SHA,b)

    def test_detects_fake_same_binary_for_both_grids(self):
        s,tov,b=self.sample();b['201x401']=b['151x301']
        with self.assertRaisesRegex(ValueError,'IDENTICAL_SOLVER_MESH_BINARIES'):
            F.audit_pair(s,tov,F.EOS_SHA,b)

    def test_detects_changed_EOS_digest(self):
        s,tov,b=self.sample()
        with self.assertRaisesRegex(ValueError,'SOURCE_OR_GRIDS_DRIFT'):
            F.audit_pair(s,tov,'f'*64,b)

    def test_detects_unphysically_unstable_mislabelled_source(self):
        s,tov,b=self.sample();tov['status']='PHYSICAL_ACCEPTED'
        with self.assertRaisesRegex(ValueError,'INCORRECT_STATIC_REFERENCE'):
            F.audit_pair(s,tov,F.EOS_SHA,b)

if __name__=='__main__': unittest.main()
