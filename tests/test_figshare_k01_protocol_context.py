"""Protocol guard regression tests. Fixtures are synthetic; live CI reads originals."""
import copy
import unittest

from research.battery_curve_audit.figshare_k01_protocol_context import (
    EXPECTED, inspect_source_receipt
)


def fixture():
    source_windows = [
        {"source_file_id": fid, "source_csv_name": f, "source_archive_sha256": sh,
         "source_window_points": 20000}
        for fid, (f, sh) in EXPECTED.items()
    ]
    pairs = [
        (47627092, 47627089, 1976, 1934, 1715, 1714, 1),
        (47627092, 47639005, 1948, 1946, 1912, 1, 1),
        (47627089, 47639005, 3186, 2942, 2571, 72, 56),
    ]
    rows = []
    for a,b,matched,step,regime,near,outliers in pairs:
        rows.append({
            "left_source_id":a, "right_source_id":b,
            "matched_unique_elapsed_time_points":matched,
            "same_step_points":step, "same_step_and_current_points":regime,
            "source_window_coverage_fraction":str(regime/20000),
            "near_2mV_voltage_pairs":near, "voltage_deltas_gt_50mV":outliers,
            "independent_cell_identity_authenticated":False,
            "physical_phase_alignment_authenticated":False,
            "field_FPR_FNR_established":False,
            "full_window_comparability_established":False,
        })
    return {
        "schema":"cano.battery.figshare279.original-three-phase-current-gate.v1",
        "source_article_id":25975315, "source_doi":"10.6084/m9.figshare.25975315.v1",
        "source_windows":source_windows, "total_source_time_voltage_points":60000,
        "pair_count":3, "pair_results":rows,
        "field_FPR_FNR_established":False, "production_release_allowed":False,
        "publisher_meta_to_physical_cell_identity_independently_verified":False,
        "independently_proven_same_test_conditions":False,
    }


class ProtocolContextTests(unittest.TestCase):
    def test_expected_early_voltage_similarity_not_duplicate_proof(self):
        out=inspect_source_receipt(fixture())
        self.assertEqual(out["decision"],
            "AUTHOR_PROTOCOL_EXPLAINS_PLAUSIBLE_NEAR_AGREEMENT_NOT_COPY_PROOF")
        d={tuple(x["source_file_ids"]):x for x in out["pair_results"]}
        self.assertEqual(d[(47627089,47627092)]["classification"],
                         "HIGH_INITIAL_TEST_NEAR_AGREEMENT_LOW_COVERAGE")
        self.assertEqual(d[(47627089,47627092)]["near_fraction_of_common_regime"],
                         "0.999417")
        self.assertEqual(d[(47627089,47627092)]["gt_50mV_outlier_observations"],1)
        self.assertFalse(d[(47627089,47627092)]["proven_duplicate_measurement"])
        self.assertFalse(out["production_release_allowed"])
        self.assertEqual(out["author_protocol_context"]["cell_numbers"],["04","05","06"])

    def test_mislabeled_archive_hash_never_trusted(self):
        x=fixture()
        x["source_windows"][0]["source_archive_sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"provenance"):inspect_source_receipt(x)

    def test_fake_stage_filename_never_trusted(self):
        x=fixture()
        x["source_windows"][0]["source_csv_name"]="TP_z01_05_01_ET_T23.csv"
        with self.assertRaisesRegex(ValueError,"provenance"):inspect_source_receipt(x)

    def test_wrong_or_duplicate_source_pair_rejected(self):
        x=fixture(); x["pair_results"][1]=copy.deepcopy(x["pair_results"][0])
        with self.assertRaisesRegex(ValueError,"duplicate"):inspect_source_receipt(x)

    def test_forged_field_acceptance_rejected(self):
        x=fixture(); x["field_FPR_FNR_established"]=True
        with self.assertRaisesRegex(ValueError,"unverified"):inspect_source_receipt(x)
        x=fixture(); x["pair_results"][0]["independent_cell_identity_authenticated"]=True
        with self.assertRaisesRegex(ValueError,"unsupported"):inspect_source_receipt(x)

    def test_coverage_mismatch_rejected(self):
        x=fixture(); x["pair_results"][0]["source_window_coverage_fraction"]="0.99"
        with self.assertRaisesRegex(ValueError,"coverage"):inspect_source_receipt(x)

    def test_impossible_near_count_rejected(self):
        x=fixture(); x["pair_results"][0]["near_2mV_voltage_pairs"]=9000
        with self.assertRaisesRegex(ValueError,"impossible"):inspect_source_receipt(x)

    def test_nonfinite_or_boolean_inputs_rejected(self):
        x=fixture(); x["pair_results"][0]["source_window_coverage_fraction"]="NaN"
        with self.assertRaisesRegex(ValueError,"nonfinite"):inspect_source_receipt(x)
        x=fixture(); x["pair_results"][0]["same_step_points"]=True
        with self.assertRaisesRegex(ValueError,"invalid count"):inspect_source_receipt(x)

    def test_malformed_or_missing_original_source_rejected(self):
        x=fixture(); x["source_windows"][1]["source_file_id"]=47627092
        with self.assertRaisesRegex(ValueError,"missing/duplicate"):inspect_source_receipt(x)
        x=fixture(); x["source_doi"]="10.6084/m9.figshare.000000"
        with self.assertRaisesRegex(ValueError,"publisher"):inspect_source_receipt(x)

    def test_small_regime_never_produces_fake_near_score(self):
        x=fixture(); row=x["pair_results"][0]
        row["same_step_and_current_points"]=250
        row["source_window_coverage_fraction"]="0.0125"
        row["near_2mV_voltage_pairs"]=None
        out=inspect_source_receipt(x)
        self.assertEqual(next(r for r in out["pair_results"] if r["source_file_ids"]==[47627089,47627092])["classification"],
                         "INSUFFICIENT_COMMON_REGIME_POINTS")
        self.assertIsNone(next(r for r in out["pair_results"] if r["source_file_ids"]==[47627089,47627092])["near_fraction_of_common_regime"])

    def test_identical_initial_trace_still_not_a_physical_duplicate_label(self):
        x=fixture(); row=x["pair_results"][0]
        row["near_2mV_voltage_pairs"]=1715
        out=inspect_source_receipt(x)
        self.assertFalse(out["physical_duplicate_established"])
        self.assertFalse(out["field_FPR_FNR_established"])


if __name__=="__main__":
    unittest.main()
