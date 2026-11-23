import datetime
import unittest
from agv_temp_stratified_qc import grouped_paired_year


class TestTemperatureMatching(unittest.TestCase):
    def test_compositional_shift_disappears_with_temperature_matching(self):
        rows=[]
        for year in (2020,2021):
            for band in (20,30):
                n=25 if (year==2020 and band==20) or (year==2021 and band==30) else 5
                for _ in range(n):
                    rows.append({"battery":"FB-0","date":datetime.date(year,1,10),
                                 "temp_band":band,"cycle":100 if band==20 else 200})
        month=grouped_paired_year(rows,False,5)["FB-0"]["weighted_pct"]
        temp=grouped_paired_year(rows,True,5)["FB-0"]["weighted_pct"]
        self.assertNotEqual(month,0)
        self.assertEqual(temp,0)

    def test_unmatched_temperatures_do_not_produce_false_result(self):
        rows=[
            {"battery":"FB-0","date":datetime.date(2020,1,10),"temp_band":20,"cycle":50},
            {"battery":"FB-0","date":datetime.date(2021,1,10),"temp_band":30,"cycle":40}
        ]
        self.assertIsNone(grouped_paired_year(rows,True,1)["FB-0"]["weighted_pct"])

    def test_zero_baseline_is_excluded(self):
        rows=[
            {"battery":"FB-0","date":datetime.date(2020,1,10),"temp_band":20,"cycle":0},
            {"battery":"FB-0","date":datetime.date(2021,1,10),"temp_band":20,"cycle":100}
        ]
        self.assertIsNone(grouped_paired_year(rows,True,1)["FB-0"]["weighted_pct"])


if __name__=="__main__":
    unittest.main()
