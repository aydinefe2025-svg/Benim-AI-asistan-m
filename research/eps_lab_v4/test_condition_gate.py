import unittest
from condition_gate import evaluate

class GateTest(unittest.TestCase):
    def setUp(self):
        self.p={'module':'1','iv':'IV/1_1_1_01022020.csv','ref':'RefIV/1_1_1_01012020.csv','days':1,'date':'2020-01-02','ref_date':'2020-01-01','iv_curve':{'sha256':'a','sampled_Pmax_W':90,'V_at_sampled_Pmax':10,'I_at_sampled_Pmax':9},'ref_curve':{'sha256':'b','sampled_Pmax_W':100,'V_at_sampled_Pmax':10,'I_at_sampled_Pmax':10},'change_pct':-10,'published_Pmp_difference_pct':0.1}
        self.m={'RefA':'9','RefRefA':'10','Measured_Temperature_(C)':'25','Simulator_Make':'SPIRE','Simulator_Model':'4600','IV_Lab_Location':'PSEL'}
        self.r=dict(self.m,RefA='10')
    def test_calibration_ratio_is_sensitivity_not_claim(self):
        r=evaluate(self.p,self.m,self.r);self.assertAlmostEqual(r['current_proxy_adjusted_change_pct'],0);self.assertEqual(r['causal_status'],'NOT_IDENTIFIED');self.assertEqual(r['status'],'CONDITION_COMPARABLE_SCREEN')
    def test_missing_reference_never_invented(self):
        r=evaluate(self.p,self.m,None);self.assertEqual(r['status'],'REFERENCE_CONDITIONS_UNVERIFIED');self.assertIsNone(r['reference_temperature_C'])
    def test_different_temperature_not_comparable(self):
        r=evaluate(self.p,self.m,dict(self.r,**{'Measured_Temperature_(C)':'30'}));self.assertEqual(r['status'],'CONDITION_DIFFERENCE')
    def test_same_content_not_independent(self):
        self.p['iv_curve']['sha256']='b';self.p['days']=0
        r=evaluate(self.p,self.m,self.r);self.assertEqual(r['status'],'SELF_REFERENCE')
    def test_invalid_calibration_is_not_silently_substituted(self):
        r=evaluate(self.p,dict(self.m,RefA='0'),self.r);self.assertIsNone(r['current_proxy_adjusted_change_pct']);self.assertEqual(r['status'],'CALIBRATION_UNVERIFIED')
    def test_voltage_current_decomposition(self):
        r=evaluate(self.p,self.m,self.r);self.assertAlmostEqual(r['log_voltage_pct'],0);self.assertAlmostEqual(r['log_current_pct'],r['log_power_pct'])
    def test_calibration_metadata_conflict(self):
        r=evaluate(self.p,self.m,dict(self.r,RefA='8'));self.assertEqual(r['status'],'CALIBRATION_CONFLICT')
    def test_mismatch_pmp_is_flagged(self):
        self.p['published_Pmp_difference_pct']=6
        r=evaluate(self.p,self.m,self.r);self.assertTrue(r['pmp_review']);self.assertEqual(r['causal_status'],'NOT_IDENTIFIED')
if __name__=='__main__':unittest.main()
