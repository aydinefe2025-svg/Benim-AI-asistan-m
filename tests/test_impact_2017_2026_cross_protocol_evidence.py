"""No false pooled safety/absolute capacity model across incompatible real studies."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1]/"research"/"battery_curve_audit"/"impact_2017_2026_cross_protocol_evidence.py"
spec=importlib.util.spec_from_file_location("impact_2017_2026_cross_protocol_evidence",PATH)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PrimaryEvidenceHeterogeneityTests(unittest.TestCase):
    def setUp(self): self.a=m.audit()

    def test_four_primary_experiments_independent_not_pooled(self):
        self.assertEqual(self.a["source_count"],4)
        self.assertEqual(len(set(s["source"] for s in m.SOURCES)),4)
        self.assertFalse(self.a["cross_protocol_pooling_allowed"])

    def test_2017_18650_crash_loss_cannot_be_converted_to_joules(self):
        s=m.SOURCES[0]
        self.assertEqual(s["capacity_loss_percent_interval"],[2.0,3.0])
        self.assertIsNone(s["impact_energy_joules"])
        self.assertTrue(self.a["cannot_convert_2017_crash_acceleration_pulse_to_joules_from_paper"])

    def test_2020_no_detected_capacity_diff_does_not_imply_no_hidden_short(self):
        s=m.SOURCES[1]
        self.assertIs(s["capacity_vs_control_significant_difference_reported"],False)
        self.assertTrue(s["hidden_high_resistance_short_circuits_reported"])
        self.assertFalse(self.a["independent_hidden_fault_corroboration"]["capacity_difference_statistically_detected"])

    def test_2025_high_retention_with_mechanical_failure_energy_damage(self):
        s=m.SOURCES[2]
        self.assertEqual(s["capacity_retained_pct_by_joule"]["3"],99.4)
        self.assertEqual(s["secondary_failure_deformation_energy_loss_pct_by_joule"]["3"],40.0)
        self.assertEqual(s["internal_resistance_increase_pct_by_joule"]["3"],4.2)

    def test_2026_seven_j_survivor_capacity_not_identifiable(self):
        self.assertEqual(m.SOURCES[3]["one_week_survival"]["7"],{"n":15,"survived":0})
        self.assertIsNone(m.SOURCES[3]["capacity_retained_pct_by_joule"])
        self.assertFalse(self.a["individual_cell_damage_capacity_function_identifiable"])

    def test_same_energy_unit_not_enough_to_merge_cohorts(self):
        self.assertIn("pouch",m.SOURCES[2]["physical_cell_format"])
        self.assertIn("pouch",m.SOURCES[3]["physical_cell_format"])
        self.assertNotEqual(m.SOURCES[2]["mechanical_protocol"],m.SOURCES[3]["mechanical_protocol"])
        self.assertTrue(self.a["nominally_same_7j_does_not_make_experiments_exchangeable"])

    def test_no_made_up_raw_data_or_inference(self):
        self.assertFalse(any(s["cross_specimen_raw_paired_capacity_public"] for s in m.SOURCES))
        self.assertTrue(self.a["no_raw_or_sensor_recalibration_claim"])
        self.assertTrue(self.a["no_2017_or_2020_p_value_fabricated"])

    def test_no_certification_from_retained_capacity(self):
        self.assertTrue(self.a["no_safety_clearance_from_capacity_alone"])
        self.assertFalse(self.a["cross_protocol_pooling_allowed"])


if __name__=="__main__":
    unittest.main()
