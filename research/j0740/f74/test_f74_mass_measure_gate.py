import unittest, pathlib, numpy as np
from f74_mass_measure_gate import pdf_grid, weighted_moments, line_integrals, infer_mass_measure, source_semantics

class MeasureGateTests(unittest.TestCase):
    def setUp(self):
        self.m=np.linspace(1.6,2.5,9001)
        self.pdf=pdf_grid(self.m,np.exp(-0.5*((self.m-2.08)/0.07)**2))
    def test_grid_pdf_integrates_exact(self):
        self.assertAlmostEqual(np.trapezoid(self.pdf,self.m),1.0,10)
    def test_mass_squared_narrows_a_gaussian(self):
        mm=weighted_moments(self.m,self.pdf)
        mm2=weighted_moments(self.m,pdf_grid(self.m,self.pdf**2))
        self.assertAlmostEqual(mm['sigma']/mm2['sigma'],2**.5,2)
    def test_source_prior_corrected_unit_likelihood_is_one(self):
        prior=self.pdf;posterior=self.pdf
        # q/pi=1, target-prior=prior, so integral is exactly unity.
        actual=np.trapezoid(prior*(posterior/prior),self.m)
        self.assertAlmostEqual(actual,1.0,10)
        # Sampling from q_M and evaluating q(M) again integrates q_M**2.
        wrong=np.trapezoid(prior*posterior,self.m)
        self.assertGreater(wrong,2.0)
    def test_grid_line_integral_correction_matches_quadrature(self):
        m=self.m
        # normalized q(M,R=R0) set to known nonnegative profile q_M*f(M)
        qline=self.pdf*(1.0+0.25*np.sin(18*m))
        right,weighted,weighted_corr=line_integrals(m,self.pdf,qline)
        self.assertAlmostEqual(right,weighted_corr,8)
        self.assertGreater(abs(weighted-right),0.3)
    def test_density_with_zero_mass_is_rejected(self):
        z=self.pdf.copy();z[25]=0
        with self.assertRaises(ValueError):line_integrals(self.m,z,self.pdf)
    def test_mass_measure_rejects_nonfinite(self):
        z=self.pdf.copy();z[10]=np.nan
        with self.assertRaises(ValueError):weighted_moments(self.m,z)
    def test_mass_measure_report(self):
        r=infer_mass_measure(self.m,self.pdf)
        self.assertTrue(r['sigma_ratio_squared_over_original']<0.75)
        self.assertTrue(r['sigma_ratio_squared_over_original']>0.67)
    def test_source_needs_original_jester_code(self):
        p=pathlib.Path(__file__).parent/'nonexistent.txt'
        with self.assertRaises(FileNotFoundError):source_semantics(p)

if __name__=='__main__': unittest.main()
