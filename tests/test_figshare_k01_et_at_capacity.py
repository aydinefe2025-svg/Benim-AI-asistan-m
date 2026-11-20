"""Fail-closed synthetic regression tests for author-method original ET/AT reader."""
import io
import unittest
from zipfile import ZipFile

from research.battery_curve_audit.figshare_k01_et_at_capacity import (
    inspect_phase, select_et_at,
)


def sample_csv(current=4.,mismatch=False,only_charge=False,duplicate_step=False,
               backwards=False,nonfinite=False):
    rows=["run_time,c_vol,c_cur,step_type"]
    for i in range(80):
        t=i*60
        if backwards and i==20: t=-999
        v="nan" if nonfinite and i==15 else "4.0"
        rows.append(f"{t},{v},{current},21")
    if not only_charge:
        for i in range(80,160):
            rows.append(f"{i*60},3.4,{-current},22")
    if duplicate_step:
        for i in range(160,170):
            rows.append(f"{i*60},4.0,{current},21")
    return "\n".join(rows)+"\n"


def example_zip(include_at=True,at_lab="LAB_A",at_serial="SERIAL_A",
                second_at=False,wrong_name=False,only_charge=False):
    stem="TP_k01_05"
    b=io.BytesIO()
    with ZipFile(b,"w") as z:
        src="TP_k01_05_01_ET_T23.csv"
        z.writestr(src, sample_csv(4,only_charge=only_charge))
        z.writestr(src[:-4]+"_meta.txt",
                   "Laboratory identifier: LAB_A\nInternal cell serial: SERIAL_A\n"
                   "Climate chamber temperature setpoint: 23\n")
        if include_at:
            src="TP_k01_05_02_AT_T23.csv" if not wrong_name else "other_02_AT_T23.csv"
            z.writestr(src,sample_csv(3.6))
            z.writestr(src[:-4]+"_meta.txt",
                       f"Laboratory identifier: {at_lab}\n"
                       f"Internal cell serial: {at_serial}\n"
                       "Climate chamber temperature setpoint: 23\n")
            if second_at:
                src="TP_k01_05_03_AT_T23.csv"
                z.writestr(src,sample_csv(3.8))
                z.writestr(src[:-4]+"_meta.txt",
                           "Laboratory identifier: LAB_A\nInternal cell serial: SERIAL_A\n")
    b.seek(0)
    return ZipFile(b)


class BatteryOriginalETATTests(unittest.TestCase):
    def test_original_author_step21_step22_current_integral(self):
        with example_zip() as z:
            d=inspect_phase(z,"TP_k01_05_01_ET_T23.csv")
        self.assertTrue(d["source_capacity_extractable"])
        self.assertEqual(d["source_rows_processed"],160)
        self.assertEqual(d["step21_charging"]["rows"],80)
        self.assertEqual(d["step22_discharging"]["rows"],80)
        self.assertAlmostEqual(d["capacity_mean_Ah"],79*60*4/3600,places=5)

    def test_round_only_after_both_raw_current_integrals(self):
        # Author capacity mean is derived from raw current-time integrals, not
        # a second rounding of each 6-decimal channel readout. This fixture
        # exposes a genuine 0.000001 Ah double-rounding boundary.
        lines=sample_csv(current=4.000059202722689).splitlines()
        for j in range(1,len(lines)):
            if lines[j].endswith(",22"):
                fields=lines[j].split(",")
                fields[2]="-4.000042374740824"
                lines[j]=",".join(fields)
        with ZipFile(io.BytesIO(),"w") as z:
            z.writestr("test.csv","\n".join(lines)+"\n")
            q=inspect_phase(z,"test.csv")
        self.assertTrue(q["source_capacity_extractable"])
        self.assertEqual(q["capacity_mean_Ah"],5.266734)

    def test_et_at_real_within_source_relative_change_only(self):
        with example_zip() as z:
            d=select_et_at(z,"TP_k01_05")
        self.assertEqual(d["decision"],"WITHIN_SOURCE_ET_AT_CAPACITY_RESEARCH_ONLY")
        self.assertAlmostEqual(d["et_at_capacity_change_percent"],-10.0,places=3)
        self.assertTrue(d["publisher_sidecar_lab_internal_serial_match"])
        self.assertFalse(d["physical_cell_identity_independently_authenticated"])
        self.assertFalse(d["aging_storage_only_causal_attribution_established"])

    def test_missing_or_ambiguous_final_source_does_not_guess(self):
        with example_zip(include_at=False) as z:
            d=select_et_at(z,"TP_k01_05")
        self.assertEqual(d["decision"],"ET_AT_T23_UNIQUE_PAIR_NOT_ESTABLISHED")
        self.assertIsNone(d["et_at_capacity_change_percent"])
        with example_zip(second_at=True) as z:
            d=select_et_at(z,"TP_k01_05")
        self.assertEqual(d["at_matches"],2)
        self.assertFalse(d["capacity_established"])

    def test_wrong_name_does_not_implicitly_match(self):
        with example_zip(wrong_name=True) as z:
            d=select_et_at(z,"TP_k01_05")
        self.assertEqual(d["at_matches"],0)
        self.assertFalse(d["capacity_established"])

    def test_original_serial_conflict_fails_closed(self):
        with example_zip(at_serial="ANOTHER_PHYSICAL_CELL") as z:
            with self.assertRaisesRegex(ValueError,"serial mismatch"):
                select_et_at(z,"TP_k01_05")

    def test_original_lab_conflict_fails_closed(self):
        with example_zip(at_lab="OTHER_LAB") as z:
            with self.assertRaisesRegex(ValueError,"lab or cell serial mismatch"):
                select_et_at(z,"TP_k01_05")

    def test_only_one_capacity_step_never_yields_fabricated_percent(self):
        with example_zip(only_charge=True) as z:
            d=select_et_at(z,"TP_k01_05")
        self.assertEqual(d["decision"],"ORIGINAL_ET_AT_CAPACITY_REVIEW_REQUIRED")
        self.assertIsNone(d["et_at_capacity_change_percent"])

    def test_nonmonotonic_clock_rejected(self):
        with ZipFile(io.BytesIO(), "w") as z:
            z.writestr("test.csv",sample_csv(backwards=True))
            with self.assertRaisesRegex(ValueError,"clock not monotonic"):
                inspect_phase(z,"test.csv")

    def test_nonfinite_voltage_fails_even_if_steps_elsewhere_valid(self):
        with ZipFile(io.BytesIO(),"w") as z:
            z.writestr("test.csv",sample_csv(nonfinite=True))
            with self.assertRaisesRegex(ValueError,"nonfinite"):
                inspect_phase(z,"test.csv")

    def test_repeat_disjoint_charge_phase_requires_manual_review(self):
        with ZipFile(io.BytesIO(),"w") as z:
            z.writestr("test.csv",sample_csv(duplicate_step=True))
            d=inspect_phase(z,"test.csv")
        self.assertEqual(d["step21_charging"]["status"],"MISSING_OR_MULTIPLE_CAPACITY_SEGMENTS")
        self.assertIsNone(d["capacity_mean_Ah"])

    def test_unexpected_source_stage_rejected(self):
        with example_zip() as z:
            with self.assertRaisesRegex(ValueError,"calendar archive"):
                select_et_at(z,"TP_z01_05")


if __name__=="__main__":
    unittest.main()
