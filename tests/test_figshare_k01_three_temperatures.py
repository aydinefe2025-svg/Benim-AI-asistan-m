"""Fail-closed 3-temperature original source parser tests with synthetic ZIPs."""
import io
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

from research.battery_curve_audit.figshare_k01_three_temperatures import (
    analyze_cell, run, TEMPERATURE_C
)
from tests.test_figshare_k01_et_at_capacity import sample_csv

STEM="TP_k01_05"


def fixture(*,missing=None,extra=None,wrong_serial=None,wrong_temp=None,
            wrong_testpoint=None,at_current=3.7,broken_voltage=False):
    b=io.BytesIO()
    with ZipFile(b,"w") as z:
        for temp in TEMPERATURE_C:
            for phase in ("ET","AT"):
                name=f"{STEM}_{'01' if phase=='ET' else '02'}_{phase}_T{temp}.csv"
                if name==missing: continue
                txt=sample_csv(4.0 if phase=="ET" else at_current)
                if broken_voltage and phase=="AT" and temp==45:
                    txt=txt.replace(",3.4,",",nan,",1)
                z.writestr(name,txt)
                serial="SERIAL_A"
                if (wrong_serial is not None and
                    phase=="AT" and temp==wrong_serial):
                    serial="OTHER"
                climate=temp if not (wrong_temp is not None and
                    phase=="AT" and temp==wrong_temp) else 99
                point="k01noCU"
                if wrong_testpoint is not None and phase=="AT" and temp==wrong_testpoint:
                    point="k01"
                z.writestr(name[:-4]+"_meta.txt",
                    f"Laboratory identifier: LAB_A\n"
                    f"Internal cell serial: {serial}\n"
                    f"Climate chamber temperature setpoint: {climate}°C\n"
                    f"Testpoint: {point}\n")
        if extra is not None:
            z.writestr(extra,sample_csv(4.0))
            z.writestr(extra[:-4]+"_meta.txt",
                "Laboratory identifier: LAB_A\n"
                "Internal cell serial: SERIAL_A\n"
                "Climate chamber temperature setpoint: 10°C\n"
                "Testpoint: k01noCU\n")
    b.seek(0)
    return ZipFile(b)


class ThreeTempTests(unittest.TestCase):
    def test_real_source_logic_three_temperature_pairs_and_no_field_claim(self):
        with fixture() as z:
            out=analyze_cell(z,STEM)
        self.assertEqual(len(out),3)
        self.assertEqual([r["temperature_C"] for r in out],[10,23,45])
        self.assertTrue(all(x["source_sidecar_identity_matched"] for x in out))
        self.assertTrue(all(x["et_to_at_change_percent"]<0 for x in out))
        self.assertFalse(any(x["physical_identity_independently_authenticated"] for x in out))
        self.assertFalse(any(x["storage_only_aging_attribution_proved"] for x in out))

    def test_warming_temperature_alone_cannot_count_as_aging(self):
        with fixture() as z:
            out=analyze_cell(z,STEM)
        self.assertEqual(out[0]["temperature_C"],10)
        self.assertEqual(out[1]["temperature_C"],23)
        self.assertEqual(out[2]["temperature_C"],45)
        self.assertEqual(len({x["et_capacity_Ah"] for x in out}),1)

    def test_provenance_mismatch_serial_fails(self):
        with fixture(wrong_serial=23) as z:
            with self.assertRaisesRegex(ValueError,"serial changed"):
                analyze_cell(z,STEM)

    def test_chamber_temperature_disagreement_fails(self):
        with fixture(wrong_temp=45) as z:
            with self.assertRaisesRegex(ValueError,"temperature mismatch"):
                analyze_cell(z,STEM)

    def test_missing_explicit_nocu_testpoint_fails(self):
        with fixture(wrong_testpoint=10) as z:
            with self.assertRaisesRegex(ValueError,"noCU testpoint"):
                analyze_cell(z,STEM)

    def test_missing_at_t23_is_not_substituted_with_other_temp(self):
        with fixture(missing=STEM+"_02_AT_T23.csv") as z:
            with self.assertRaisesRegex(ValueError,"missing or ambiguous"):
                analyze_cell(z,STEM)

    def test_duplicate_et_t10_is_ambiguous(self):
        with fixture(extra=STEM+"_03_ET_T10.csv") as z:
            with self.assertRaisesRegex(ValueError,"missing or ambiguous"):
                analyze_cell(z,STEM)

    def test_nonfinite_physical_source_fails_closed(self):
        with fixture(broken_voltage=True) as z:
            with self.assertRaisesRegex(ValueError,"nonfinite"):
                analyze_cell(z,STEM)

    def test_positive_capacity_change_is_reported_not_censored(self):
        with fixture(at_current=4.3) as z:
            out=analyze_cell(z,STEM)
        self.assertTrue(all(x["et_to_at_change_percent"]>0 for x in out))
        self.assertFalse(any(x["storage_only_aging_attribution_proved"] for x in out))

    def test_wrong_archive_family_fails(self):
        with fixture() as z:
            with self.assertRaisesRegex(ValueError,"unexpected original"):
                analyze_cell(z,"TP_z01_05")

    def test_no_fake_offline_data_when_publisher_zip_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,"missing/changed"):
                run(Path(tmp))

    def test_invalid_offline_directory_fails_before_network(self):
        with self.assertRaisesRegex(ValueError,"no offline source directory"):
            run(Path("/path/does/not/exist"))


if __name__=="__main__":
    unittest.main()
