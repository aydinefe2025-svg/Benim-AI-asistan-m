from pathlib import Path
import math,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import f83_real_c_compare as F

class CompareTests(unittest.TestCase):
    def star(self, g):return {'status':'ACTUAL_DIRECT_C_TWO_CONSTRAINT_PASS_NOT_PHYSICAL_EOS_STABILITY',
       'M_msun':2.073,'spin_hz':346.536369,'R_equatorial_km':12.528 + g/2000,
       'J_cgs':6.06e48,'trace':[{'x':i} for i in range(5)],'direct_C_evaluations':5}
    def old(self,g):return {'M_msun':2.073,'spin_hz':346.536369,'R_equatorial_km':12.529+g/2000,'J_cgs':6.06e48}
    def test_real_observed_mass_spin_and_old_new_not_same_model(self):
        d=F.compare_new_old({'151x301':self.star(0),'201x401':self.star(1)},
           {'151x301':self.old(0),'201x401':self.old(1)},'a'*64,F.F83.EOS_SHA)
        self.assertEqual(d['status'],'NEW_PIECEWISE_INTEGRABLE_SOURCE_REAL_TWO_GRID_C_NUMERICAL_PASS')
        self.assertEqual(d['Gibbs_BPS_core_phase_thermodynamics'],'NOT_ESTABLISHED')
        self.assertEqual(d['XPSI_full_native_photon_likelihood'],'NOT_RUN')
    def test_fake_C_star_not_accepted(self):
        a={'151x301':self.star(0),'201x401':self.star(1)};a['201x401']['status']='SYNTHETIC'
        with self.assertRaisesRegex(ValueError,'NOT_GENUINE'):F.compare_new_old(a,{'151x301':self.old(0),'201x401':self.old(1)},'a'*64,F.F83.EOS_SHA)
    def test_bad_J_not_accepted(self):
        a={'151x301':self.star(0),'201x401':self.star(1)};a['151x301']['J_cgs']=0
        with self.assertRaisesRegex(ValueError,'TRACE_OR_J'):F.compare_new_old(a,{'151x301':self.old(0),'201x401':self.old(1)},'a'*64,F.F83.EOS_SHA)
    def test_bad_frequency_refused(self):
        a={'151x301':self.star(0),'201x401':self.star(1)};a['151x301']['spin_hz']+=.02
        with self.assertRaisesRegex(ValueError,'MASS_OR_SPIN'):F.compare_new_old(a,{'151x301':self.old(0),'201x401':self.old(1)},'a'*64,F.F83.EOS_SHA)

if __name__=='__main__':unittest.main()
