import copy
import unittest

from gka_final_owner_replay import EXPECTED_AGV_MD5, STAGES, verify_documents


def synthetic_receipts():
    shas={"TSURU":"a"*64,"UGUISU":"b"*64,"RAAVANA":"c"*64,"NEPALISAT":"d"*64}
    source_sha="e"*64
    r={k:{"status":expected} for k,_,_,expected in STAGES}
    r["source"].update({
        "tsuru":{"sha256":shas["TSURU"],"rows_excluding_headers":26023},
        "agv":{"sha256":source_sha,"md5":EXPECTED_AGV_MD5,"rows":57880,"packs":10},
    })
    r["four_birds"]["satellites"]={name:{"sha256":val} for name,val in shas.items()}
    r["panel"]["satellites"]={name:{"sha256":val} for name,val in shas.items()}
    r["panel"]["independent_physical_fault_confirmation"]=False
    r["population"]["original_three_birds"]={
        "source_rows":8469, "source_rows_outside_paper_window_by_sheet":7390}
    r["population"]["acceptance"]={
        "paper_8439_same_population_as_original_workbooks":False,
        "published_test_metrics_reproduced":False}
    r["temperature"]["agv_sha256"]=source_sha
    r["day_cluster"]["source_sha256"]=source_sha
    r["day_cluster"]["source_n_rows"]=57880
    r["day_cluster"]["results"]={f"FB-{i}":{
        "temperature_stratified_pct":(-10.0 if i<5 else 10.0)}
        for i in range(10)}
    r["month_block"].update({
        "input_source_sha256":source_sha, "source_rows":57880,
        "negative_estimate_packs":5,"positive_estimate_packs":5,
        "interval_excludes_zero_packs":["FB-1"],
        "packs":{f"FB-{i}":{"estimate_pct":(-10.0 if i<5 else 10.0)}
                 for i in range(10)},
    })
    return r


class FinalReplayControls(unittest.TestCase):
    def test_complete_receipt_accepts_pinned_structural_evidence(self):
        self.assertEqual(verify_documents(synthetic_receipts())[
            "original_agv_events"],57880)

    def test_reject_source_cross_identity_mismatch(self):
        data=synthetic_receipts()
        data["panel"]["satellites"]["TSURU"]["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"TSURU"):
            verify_documents(data)

    def test_reject_false_paper_label_reproduction(self):
        data=synthetic_receipts()
        data["population"]["acceptance"]["published_test_metrics_reproduced"]=True
        with self.assertRaisesRegex(ValueError,"benchmark"):
            verify_documents(data)

    def test_reject_causal_fault_claim(self):
        data=synthetic_receipts()
        data["panel"]["independent_physical_fault_confirmation"]=True
        with self.assertRaisesRegex(ValueError,"physical fault"):
            verify_documents(data)

    def test_reject_stale_agv_sensitivity_direction(self):
        data=synthetic_receipts()
        data["month_block"]["interval_excludes_zero_packs"]=["FB-0","FB-1"]
        with self.assertRaisesRegex(ValueError,"month-pair"):
            verify_documents(data)

    def test_reject_wrong_source_status(self):
        data=synthetic_receipts()
        data["source"]["status"]="SYNTHETIC_ONLY"
        with self.assertRaisesRegex(ValueError,"unexpected status"):
            verify_documents(data)

    def test_reject_deceptive_same_size_different_agv(self):
        data=synthetic_receipts()
        data["day_cluster"]["source_sha256"]="a"*64
        with self.assertRaisesRegex(ValueError,"AGV publisher identity"):
            verify_documents(data)


if __name__=="__main__":
    unittest.main()
