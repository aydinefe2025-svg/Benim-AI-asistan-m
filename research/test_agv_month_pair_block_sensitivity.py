#!/usr/bin/env python3
"""Synthetic controls for calendar-month-paired AGV sensitivity; no real-data claims."""
import datetime
import unittest
from agv_day_cluster_common_support import support_by_pack
from agv_month_pair_block_sensitivity import evaluate,audit,sign_test_two_sided,aggregate,quantile


def rows_by_month(changes, days=4, events_per_day=6):
    out=[]
    for month,delta in sorted(changes.items()):
        for year in (2020,2021):
            for day in range(1,days+1):
                for event in range(events_per_day):
                    out.append({
                        "battery":"FB-T","date":datetime.date(year,month,day),
                        "temp_band":20,
                        "cycle":100 if year==2020 else 100+delta
                    })
    return out


class TestMonthBlocks(unittest.TestCase):
    def test_all_months_consistently_positive(self):
        groups,_=support_by_pack(rows_by_month({1:10,2:10,3:10,4:10}))
        v=evaluate(groups["FB-T"],n_draw=50)
        self.assertEqual(v["independent_calendar_month_pair_count"],4)
        self.assertAlmostEqual(v["estimate_pct"],10)
        self.assertEqual(v["paired_month_bootstrap_95pct_exploratory_interval"],[10,10])
        self.assertAlmostEqual(v["month_sign_test_two_sided_exploratory_p"],0.125)
        self.assertEqual(v["leave_one_month_out_crosses_zero_sign_count"],0)

    def test_dependence_bootstrap_determinism(self):
        groups,_=support_by_pack(rows_by_month({1:20,2:-20,3:12,4:-5}))
        a=evaluate(groups["FB-T"],n_draw=300,seed=17)
        b=evaluate(groups["FB-T"],n_draw=300,seed=17)
        self.assertEqual(a,b)
        self.assertEqual(a["paired_month_resampling_draws"],300)
        self.assertFalse(a["paired_month_interval_excludes_zero"])

    def test_low_month_count_no_95_percent_claim(self):
        groups,_=support_by_pack(rows_by_month({1:10,2:10}))
        v=evaluate(groups["FB-T"],n_draw=80)
        self.assertTrue(v["insufficient_month_pairs"])
        self.assertEqual(v["paired_month_resampling_draws"],0)
        self.assertEqual(v["paired_month_bootstrap_95pct_exploratory_interval"],[None,None])

    def test_no_support_does_not_generate_effect(self):
        groups,_=support_by_pack(rows_by_month({1:5,2:10},days=2),min_events=12,min_days=3)
        v=evaluate(groups["FB-T"],n_draw=30)
        self.assertIsNone(v["estimate_pct"])
        self.assertEqual(v["independent_calendar_month_pair_count"],0)

    def test_paired_year_eligibility_both_sides(self):
        data=rows_by_month({1:10,2:10,3:10,4:10})
        data=[r for r in data if not (r["date"].year==2021 and r["date"].month==4)]
        result=audit(data,n_draw=20)
        p=result["packs"]["FB-T"]
        self.assertEqual(p["independent_calendar_month_pair_count"],3)
        self.assertTrue(p["insufficient_month_pairs"])

    def test_small_exact_sign_p_and_empty_quantiles(self):
        self.assertAlmostEqual(sign_test_two_sided([-3,-2,-1]),0.25)
        self.assertIsNone(sign_test_two_sided([0,0]))
        self.assertIsNone(quantile([],0.5))
        self.assertEqual(quantile([0,100],0.25),25)

    def test_kish_weight_concentration(self):
        groups,_=support_by_pack(rows_by_month({1:10,2:10,3:10,4:10}))
        v=evaluate(groups["FB-T"],n_draw=15)
        self.assertEqual(v["kish_effective_weighted_month_pairs"],4)
        self.assertEqual(v["largest_month_weight_fraction"],0.25)


if __name__=="__main__":
    unittest.main()
