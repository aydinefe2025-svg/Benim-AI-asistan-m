"""Regression tests for author-example percent-SOC axis and provenance guards."""
import math
import sys
import tempfile
import unittest
from pathlib import Path

# The general Core test matrix intentionally installs no scientific packages.
# Only the existing source-backed scientific job installs numpy/pandas/scipy.
# Do NOT make all general CI jobs depend on large numerical wheels.
try:
    import numpy as np
    import pandas as pd
except ModuleNotFoundError as e:
    if e.name not in {"numpy", "pandas"}:
        raise
    np = pd = None

if np is not None and pd is not None:
    try:
        from research.battery_curve_audit.author_soc_units_audit import (
            check_soc_capacity_axis, author_pulse_view, author_reproduction, audit,
        )
    except ModuleNotFoundError as e:
        if e.name == "research":
            from author_soc_units_audit import (
                check_soc_capacity_axis, author_pulse_view, author_reproduction, audit,
            )
        elif e.name == "scipy":
            np = pd = None
        else:
            raise


def synthetic_pulse_df():
    """Only a synthetic unit fixture. All scientific claims use authentic files."""
    rest = [{'run_time':float(t),'c_cur':0.0,'c_vol':3.75,'step_type':0}
            for t in (-60,-50,-40,-30,-20,-10,-.1)]
    rows=[]
    for k in range(1503):
        t=k*.02
        i=0.0 if k==0 or k==1502 else -4.9
        v=3.75 if k==0 or k==1502 else 3.62-.0005*t
        rows.append({'run_time':t,'c_cur':i,'c_vol':v,'step_type':5032})
    rest_after=[{'run_time':31.0,'c_cur':0.0,'c_vol':3.73,'step_type':0}]
    return pd.DataFrame(rest+rows+rest_after)


@unittest.skipUnless(np is not None and pd is not None, "Scientific NumPy/Pandas/SciPy only in dedicated publisher-source CI")
class OriginalAuthorAxisTests(unittest.TestCase):
    def test_percent_axis_has_exact_100_fold_range(self):
        s=np.linspace(0,100,1001)
        large=check_soc_capacity_axis(s,4.8,1)
        fixed=check_soc_capacity_axis(s,4.8,100)
        self.assertEqual(float(large[-1]),480.0)
        self.assertEqual(float(fixed[-1]),4.8)
        np.testing.assert_allclose(large,100*fixed,rtol=0,atol=1e-13)

    def test_reject_invalid_scale(self):
        with self.assertRaisesRegex(ValueError,'scale'):
            check_soc_capacity_axis(np.array([0,50,100]),4.8,10)

    def test_reject_negative_or_outlier_capacity(self):
        for q in (-4.8,0,2,7,float('nan')):
            with self.subTest(q=q),self.assertRaises(ValueError):
                check_soc_capacity_axis(np.array([0,50,100]),q,100)

    def test_reject_so_c_percent_endpoints(self):
        for soc in ([0,.5,1],[10,50,100],[0,100,100],[0,50,101]):
            with self.subTest(soc=soc),self.assertRaises(ValueError):
                check_soc_capacity_axis(np.array(soc),4.8,100)

    def test_disallow_nonfinite_SOC(self):
        with self.assertRaises(ValueError):
            check_soc_capacity_axis(np.array([0,float('inf'),100]),4.8,100)

    def test_allow_nondegenerate_source_percent_SOC(self):
        x=check_soc_capacity_axis(np.linspace(0,100,1001),4.9,100)
        self.assertAlmostEqual(float(x[500]),2.45,places=12)

    def test_pulse_view_reproduces_published_window(self):
        df=synthetic_pulse_df()
        p=author_pulse_view(df)
        self.assertGreater(len(p),1400)
        self.assertEqual(int((p.step_type==5032).sum()),1503)
        self.assertLess(float(p.run_time.iloc[0]),0)

    def test_pulse_fail_closed_on_duplicate_segment(self):
        df=synthetic_pulse_df()
        df.loc[40,'step_type']=0
        with self.assertRaisesRegex(ValueError,'noncontiguous'):
            author_pulse_view(df)

    def test_strict_author_rejects_early_trigger_without_baseline(self):
        df=synthetic_pulse_df()
        soc=np.linspace(0,100,1001);ocv=np.linspace(3.2,4.1,1001)
        with self.assertRaisesRegex(ValueError,'author_voltage_trigger'):
            author_reproduction(df,soc,ocv,4.8,scale=1,baseline_mode='author')

    def test_fixed_fraction_axis_has_measurably_stronger_ocv_correction(self):
        df=synthetic_pulse_df()
        soc=np.linspace(0,100,1001);ocv=np.linspace(3.2,4.1,1001)
        old=author_reproduction(df,soc,ocv,4.8,scale=1,baseline_mode='rest_65s')
        fixed=author_reproduction(df,soc,ocv,4.8,scale=100,baseline_mode='rest_65s')
        self.assertTrue(math.isfinite(old['R_mohm']) and math.isfinite(fixed['R_mohm']))
        self.assertLess(fixed['R_mohm'],old['R_mohm'])
        self.assertGreater(abs(fixed['OCV_correction_mV']),50*abs(old['OCV_correction_mV']))

    def test_reject_missing_stable_pre_pulse_rest(self):
        df=synthetic_pulse_df();df.loc[df.step_type==0,'c_cur']=4.9
        with self.assertRaisesRegex(ValueError,'missing_stable_pre_pulse_rest'):
            author_reproduction(df,np.linspace(0,100,1001),np.linspace(3.2,4.1,1001),4.8,100,baseline_mode='rest_65s')

    def test_reject_nonexistent_publisher_archives(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'missing or wrong source original size'):
                audit(Path(d))


if __name__=='__main__':
    unittest.main()