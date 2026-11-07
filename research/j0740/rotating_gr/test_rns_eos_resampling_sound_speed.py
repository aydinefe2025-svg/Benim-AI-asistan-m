import unittest
import numpy as np
from rns_eos_resampling_sound_speed import eos_table_slopes,audit,C_CGS

def synthetic():
    rho=np.geomspace(1e12,2e15,196)
    p=0.5*C_CGS**2*rho
    return np.column_stack((rho,p,np.linspace(1,2,len(rho)),np.linspace(1,2,len(rho))))

class RNSTableSlopesTests(unittest.TestCase):
    def test_linear_eos_secant_and_log_slopes(self):
        rows=synthetic()
        x=eos_table_slopes(rows,1.3e15)
        self.assertAlmostEqual(x["table_secant_dp_de"],0.5,places=7)
        self.assertAlmostEqual(x["table_local_powerlaw_dp_de"],0.5,places=7)
        self.assertTrue(x["rns_table_pressure_monotone"])

    def test_near_upper_edge_no_extrapolation(self):
        rows=synthetic()
        with self.assertRaisesRegex(ValueError,"support"):
            eos_table_slopes(rows,4e15)

    def test_unphysical_nonmonotonic_density_rejected(self):
        rows=synthetic()
        rows[12,0]=rows[11,0]
        with self.assertRaisesRegex(ValueError,"Invalid"):
            eos_table_slopes(rows,1.3e15)

    def test_nonmonotonic_pressure_rejected(self):
        rows=synthetic()
        rows[44,1]=rows[43,1]
        with self.assertRaisesRegex(ValueError,"Invalid"):
            eos_table_slopes(rows,1.3e15)

    def test_not_the_same_as_global_source_cs2(self):
        rows=synthetic()
        rho=rows[:,0]
        rows[:,1]=C_CGS**2*rho**1.6/(rho[0]**.6)*.12
        x=eos_table_slopes(rows,1.2e15)
        self.assertGreater(x["table_secant_dp_de"],0)
        self.assertGreater(x["table_local_powerlaw_dp_de"],0)

    def test_RNS_source_validation_no_partial(self):
        with self.assertRaisesRegex(ValueError,"identity"):
            audit({"status":"PARTIAL_NOT_FINAL"},None,None)

if __name__=="__main__":unittest.main()
