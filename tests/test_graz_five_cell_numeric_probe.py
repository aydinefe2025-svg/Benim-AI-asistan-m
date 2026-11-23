"""Different goal from ZIP structure: inspect raw numeric rows and SP metadata."""
import io
import zipfile
import unittest
from research.battery_curve_audit import graz_five_cell_numeric_probe as m


def artificial_zip(reverse=False):
    b=io.BytesIO()
    with zipfile.ZipFile(b,"w") as z:
        for k in ("01","02","03","04","05"):
            rows=["Time, Device, Voltage, Current, Power",
                  "2024-06-12_15-15-07-000000, COM3, 3.4, 0, 0",
                  "2024-06-12_15-15-08-000000, COM3, 3.3, 1, 3.3",
                  "2024-06-12_15-15-09-000000, COM3, 3.2, 2, 6.4"]
            if reverse:
                rows[2],rows[3]=rows[3],rows[2]
            z.writestr("study/Fresh cell "+k+"/trace.log","\n".join(rows)+"\n")
            for s in range(3):
                z.writestr(f"study/Fresh cell {k}/SP_test_{s}_logfile.txt",
                           "Test  : fixture\nSpecimen : ----\nTime s\n")
    return b.getvalue()


class TestFiveRealLogNumericProbe(unittest.TestCase):
    def test_exact_five_source_folder_layout(self):
        with zipfile.ZipFile(io.BytesIO(artificial_zip())) as z:
            x=m.filename_groups(z.infolist())
            self.assertEqual(len(x),5)
            self.assertTrue(all(len(s["cycling_log"])==1 and len(s["sp_txt"])==3 for s in x.values()))

    def test_numeric_timestamp_current_arithmetic_not_capacity(self):
        with zipfile.ZipFile(io.BytesIO(artificial_zip())) as z:
            name=m.filename_groups(z.infolist())["01"]["cycling_log"][0]
            x=m.scan_electrical_log(z,name)
            self.assertEqual(x["counts"]["numeric_timestamp_rows"],3)
            self.assertEqual(x["counts"]["time_intervals_integrated"],2)
            self.assertAlmostEqual(x["bounded_signed_current_numeric_times_seconds_trapezoid"],2.0)
            self.assertAlmostEqual(x["bounded_signed_current_numeric_times_seconds_right_endpoint"],3.0)
            self.assertTrue(x["current_header_has_no_declared_unit"])
            self.assertTrue(x["not_absolute_Ah_capacity"])
            self.assertTrue(x["not_a_discharge_cycle_integral"])

    def test_time_reversals_not_integrated_as_negative_interval(self):
        with zipfile.ZipFile(io.BytesIO(artificial_zip(reverse=True))) as z:
            name=m.filename_groups(z.infolist())["01"]["cycling_log"][0]
            x=m.scan_electrical_log(z,name)
            self.assertEqual(x["counts"]["nonpositive_time_steps"],1)
            self.assertEqual(x["counts"]["time_intervals_integrated"],1)

    def test_sp_header_is_not_sensor_calibration_or_identity(self):
        with zipfile.ZipFile(io.BytesIO(artificial_zip())) as z:
            name=m.filename_groups(z.infolist())["01"]["sp_txt"][0]
            x=m.probe_sp_header(z,name)
            self.assertFalse(x["time_and_force_field_units_verified"])
            self.assertFalse(x["physical_specimen_identifier_automatically_verified"])
            self.assertTrue(any("Specimen" in t for t in x["first_100_line_metadata_matches"]))

    def test_missing_sp_or_double_log_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,"w") as z:
            z.writestr("Fresh cell 01/a.log","Time, Device, Voltage, Current, Power\n")
        with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:
            with self.assertRaisesRegex(ValueError,"not exactly one"):
                m.filename_groups(z.infolist())


if __name__=="__main__":
    unittest.main()
