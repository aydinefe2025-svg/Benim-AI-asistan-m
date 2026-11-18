import io,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
sys.path.insert(0,str(Path(__file__).resolve().parent))
import causal_apr4_fixed_spin_marginal_evidence as f

class TestF39(unittest.TestCase):
    def test_mass_radio_prior_window_probability(self):
        self.assertAlmostEqual(f.norm_radio_mass_window(), .8226993711585673, places=11)
    def test_mass_conditional_density_normalized(self):
        m=np.linspace(f.M_MIN,f.M_MAX,4001)
        self.assertAlmostEqual(simpson(f.normalized_window_pdf(m),x=m),1,places=5)
    def test_source_grid_manifest_size(self):
        self.assertEqual(len(f.SOURCE_F38_GRID_HASH),6)
        self.assertEqual(len(set(f.SOURCE_F38_GRID_HASH.values())),6)
    def test_inverted_mass_window_rejected(self):
        with self.assertRaises(ValueError):f.norm_radio_mass_window(2.3,2.2)
    def test_corrupt_f38_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'posterior_prior_ratio_weighted_0.025_0.35.npz'
            p.write_bytes(b'corrupted')
            with self.assertRaises(ValueError):f.read_likelihood(p)
    def test_constant_likelihood_expected_one(self):
        m=np.linspace(1.7305,2.4335,401)
        r=np.linspace(4.43983244,15.9900429,581)
        like=np.ones((401,581))
        support=np.ones_like(like,dtype=bool)
        prior=np.ones_like(like)
        curve=[{'target_mass_msun':float(M),'radius_eq_km':10.8} for M in np.linspace(f.M_MIN,f.M_MAX,25)]
        with patch.object(f,'read_likelihood',return_value=(m,r,like,support,prior)):
            result=f.analyze_grid('synthetic',curve)
            self.assertAlmostEqual(result['curve_conditional_L_over_Z'],1,places=5)
            self.assertAlmostEqual(result['model_to_flexible_envelope_fraction'],1,places=9)
    def test_known_mass_axis_bounds(self):
        m=np.linspace(f.M_MIN,f.M_MAX,25)
        self.assertTrue(np.all(np.diff(m)>0))
        self.assertAlmostEqual(m[-1],2.15)
if __name__=='__main__':unittest.main()