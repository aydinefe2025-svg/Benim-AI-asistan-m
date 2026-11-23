import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from research.battery_curve_audit import graz_five_sp_start_window_screen as m


def synthetic_sp(local_string: str):
    local=dt.datetime.strptime(local_string,"%d_%m_%Y_%H_%M_%S")
    ep=local.replace(tzinfo=ZoneInfo("Europe/Vienna")).timestamp()
    return {"source_member":"study/Fresh cell 03/SP_test_"+local_string+"_logfile.txt",
            "first_100_line_metadata_matches":[f"Start time : {ep}"]}


class TestSourceStartScreen(unittest.TestCase):
    def test_start_inside_and_outside_from_original_headers(self):
        cell={"electric_log":{"first_valid_timestamp":"2025-09-04T10:00:00",
                              "last_valid_timestamp":"2025-09-07T03:34:30"},
              "sp_logs":[synthetic_sp("04_09_2025_10_16_47"),
                         synthetic_sp("09_09_2025_12_50_53"),
                         synthetic_sp("10_09_2025_08_17_34")]}
        s=m.analyze_cell("03",cell)
        self.assertEqual([x["sp_start_within_electric_recording_window_candidate"] for x in s],
                         [True,False,False])
        self.assertTrue(all(not x["definite_same_cell_mechanical_electric_signal_join"] for x in s))

    def test_wrong_instrument_clock_label_rejected(self):
        bad=synthetic_sp("04_09_2025_10_16_47")
        bad["first_100_line_metadata_matches"]=["Start time: 1700000000"]
        cell={"electric_log":{"first_valid_timestamp":"2025-09-04T10:00:00",
                              "last_valid_timestamp":"2025-09-07T03:34:30"},
              "sp_logs":[bad]}
        with self.assertRaisesRegex(ValueError,"disagreement"):
            m.analyze_cell("03",cell)

    def test_wrong_record_id_is_not_coerced(self):
        with self.assertRaisesRegex(ValueError,"source identity"):
            m.analyze_real_probe({"publisher_doi":"10.5281/zenodo.18315429","cells":{}})
