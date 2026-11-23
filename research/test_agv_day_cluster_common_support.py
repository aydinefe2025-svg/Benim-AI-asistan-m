#!/usr/bin/env python3
"""Deterministic synthetic unit checks; scientific result still needs original CSV."""
import datetime
import unittest
from agv_day_cluster_common_support import support_by_pack,calculate,audit,quantile


def make(pack="FB-0",n_days=3,months=(1,),left=100,right=110):
    rows=[]
    for year,value in [(2020,left),(2021,right)]:
        for month in months:
            for day in range(1,n_days+1):
                rows.append({"battery":pack,"date":datetime.date(year,month,day),
                             "temp_band":20,"cycle":value})
    return rows


class TestControls(unittest.TestCase):
    def test_insufficient_distinct_days_fail_closed(self):
        groups,ex=support_by_pack(make(n_days=2),min_events=2,min_days=3)
        self.assertEqual(groups["FB-0"],{})
        self.assertTrue(ex["insufficient_unique_days"]>0)

    def test_equal_support_no_temperature_imbalance(self):
        groups,_=support_by_pack(make(n_days=5),min_events=5,min_days=3)
        r=calculate(groups["FB-0"])
        self.assertAlmostEqual(r["temperature_stratified_pct"],10)
        self.assertAlmostEqual(r["same_support_month_pooled_pct"],10)
        self.assertAlmostEqual(r["equal_stratum_weight_pct"],10)

    def test_day_cluster_determinism_and_month_holdout(self):
        rows=make(n_days=5,months=(1,2),left=100,right=90)
        a=audit(rows,draws=25,min_events=5,min_days=3)
        b=audit(rows,draws=25,min_events=5,min_days=3)
        self.assertEqual(a,b)
        v=a["results"]["FB-0"]
        self.assertEqual(v["supported_months"],2)
        self.assertAlmostEqual(v["temperature_stratified_pct"],-10)
        self.assertEqual(v["leave_one_month_out_opposite_sign_count"],0)
        self.assertEqual(v["day_stratified_bootstrap_draws_valid"],25)

    def test_no_fabricated_effect_on_zero_baseline(self):
        groups,ex=support_by_pack(make(n_days=5,left=0,right=100),min_events=5,min_days=3)
        self.assertEqual(groups["FB-0"],{})
        self.assertEqual(ex["zero_baseline_median"],1)

    def test_percentile_bounds(self):
        self.assertIsNone(quantile([],0.5))
        self.assertEqual(quantile([0,10],.25),2.5)


if __name__=="__main__":
    unittest.main()
