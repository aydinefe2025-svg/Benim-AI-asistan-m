"""Regression against original JESTER/LALSimulation APR4 TOV/MR-Lambda source.

The old Love Q implementation omitted the metric denominator on -6/r**2.
These tests must fail on that earlier implementation, then pass after its
physics correction. Never treat a green test as full EOS/likelihood validation.
"""
from __future__ import annotations
import math
from pathlib import Path
import unittest
import numpy as np

from tov_love_apr4_native_crust_exploratory_20261117 import EOS, solve_star, TARGET_MSUN, SOURCE_SHA, sha256

NPZ=Path(__file__).resolve().parents[3] / "jester-source/jesterTOV/tabulated_eos/lalsuite/APR4_EPP.npz"
PC=5.58247372651056e-10

class TestAPR4LoveQMetricFactor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NPZ.is_file(): raise FileNotFoundError("Pinned APR4 source required")
        if sha256(NPZ)!=SOURCE_SHA: raise ValueError("Pinned APR4 source SHA mismatch")
        cls.solution=solve_star(EOS(NPZ), PC, max_step=200.0, rtol=2e-8)
        with np.load(NPZ,allow_pickle=False) as z:
            m=np.asarray(z["masses_EOS"],float)
            r=np.asarray(z["radii_EOS"],float)
            lam=np.asarray(z["Lambda_EOS"],float)
        target=TARGET_MSUN
        crossing=np.where((m[:-1]-target)*(m[1:]-target)<=0)[0]
        if crossing.size!=1:
            raise ValueError("Non-unique JESTER target-mass crossing")
        i=int(crossing[0])
        w=(target-m[i])/(m[i+1]-m[i])
        cls.source_r=float(r[i]+w*(r[i+1]-r[i]))
        cls.source_lambda=float(lam[i]+w*(lam[i+1]-lam[i]))
        assert cls.source_lambda>0

    def test_mass_and_radius_agree_with_source_tov(self):
        self.assertAlmostEqual(self.solution["Mg_msun"],TARGET_MSUN,delta=0.002)
        self.assertAlmostEqual(self.solution["R_km"],self.source_r,delta=0.02)

    def test_tidal_lambda_agrees_with_original_lalsuite(self):
        self.assertGreater(self.solution["Lambda"],0)
        difference=abs(self.solution["Lambda"]/self.source_lambda-1)
        self.assertLess(difference,0.02,
            "TOV-Love Q likely missing metric factor in -6/[r²(1-2m/r)]")

if __name__=="__main__":
    unittest.main()
