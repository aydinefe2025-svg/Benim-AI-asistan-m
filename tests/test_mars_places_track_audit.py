"""NASA PDS PLACES tactical localization verification; no synthetic terrain claims."""
from __future__ import annotations

import csv
import io
import unittest
from pathlib import Path

from research.mars_places_track_audit import audit_csv_text


DATA = (Path(__file__).resolve().parents[1] / "research" / "data" /
        "mars2020_places_best_tactical_20260317.csv")


def local_rows(count=3):
    """Use actual pinned PDS ROVER rows for mutation regressions."""
    with DATA.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        rows = [r for r in reader if r["frame"] == "ROVER"
                and int(r["sol"]) >= 0 and int(r["sclk"]) > 0][:count]
    assert headers and len(rows) == count
    return headers, rows


def as_csv(headers, rows):
    target = io.StringIO(newline="")
    writer = csv.DictWriter(target, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return target.getvalue()


class RealMarsPlacesTrackTests(unittest.TestCase):
    def test_full_public_pds_rows_reproduced(self):
        x = audit_csv_text(DATA.read_text(encoding="utf-8"))
        self.assertEqual(x["source_kind"], "NASA_PDS_MARS2020_PLACES_BEST_TACTICAL")
        self.assertEqual(x["total_records"], 666)
        self.assertEqual(x["source_site_records"], 88)
        self.assertEqual(x["source_rover_records"], 578)
        self.assertEqual(x["validated_rover_positions"], 577)
        self.assertEqual(x["first_sol"], 13)
        self.assertEqual(x["last_sol"], 1896)

    def test_real_waypoint_distance_is_observed_chord_not_odometry(self):
        x = audit_csv_text(DATA.read_text(encoding="utf-8"))
        self.assertEqual(x["chord_segment_count"], 576)
        self.assertAlmostEqual(x["chord_sum_km"], 36.834, delta=0.005)
        self.assertGreater(x["longest_observed_chord_m"], 500)
        self.assertEqual(x["distance_interpretation"],
                         "sum_of_straight_line_separations_between_sparse_localizations_not_odometry")

    def test_coordinate_frames_and_orientation_are_internally_consistent(self):
        x = audit_csv_text(DATA.read_text(encoding="utf-8"))
        self.assertLessEqual(x["max_origin_offset_residual_m"], 0.002)
        self.assertLess(x["max_quaternion_norm_error"], 0.000001)
        self.assertEqual(x["coordinate_reference"], "landing_xyz_to_PDS_northing_easting_elevation")

    def test_no_unmeasured_hazard_energy_or_life_claims(self):
        x = audit_csv_text(DATA.read_text(encoding="utf-8"))
        self.assertFalse(x["terrain_hazard_measured"])
        self.assertFalse(x["battery_energy_measured"])
        self.assertFalse(x["life_detected"])
        self.assertTrue(x["rover_telemetry_subset_only"])

    def test_site_rows_are_not_rover_positions(self):
        x = audit_csv_text(DATA.read_text(encoding="utf-8"))
        self.assertEqual(x["source_site_records"] + x["source_rover_records"],
                         x["total_records"])

    def test_real_subset_can_be_audited_in_reversed_file_order(self):
        header, rows = local_rows()
        a = audit_csv_text(as_csv(header, rows))
        b = audit_csv_text(as_csv(header, list(reversed(rows))))
        self.assertEqual(a["chord_sum_km"], b["chord_sum_km"])
        self.assertEqual(a["first_sol"], b["first_sol"])

    def test_truncated_row_is_refused(self):
        header, rows = local_rows()
        data = as_csv(header, rows)
        with self.assertRaises(ValueError):
            audit_csv_text(data + "ROVER,broken,record\n")

    def test_duplicate_site_drive_is_refused(self):
        header, rows = local_rows()
        with self.assertRaises(ValueError):
            audit_csv_text(as_csv(header, rows + [dict(rows[0])]))

    def test_nonfinite_coordinate_is_refused(self):
        header, rows = local_rows()
        rows[1]["northing"] = "NaN"
        with self.assertRaises(ValueError):
            audit_csv_text(as_csv(header, rows))

    def test_coordinate_frame_tampering_is_refused(self):
        header, rows = local_rows()
        rows[1]["easting"] = str(float(rows[1]["easting"]) + 15)
        with self.assertRaises(ValueError):
            audit_csv_text(as_csv(header, rows))

    def test_corrupt_quaternion_is_refused(self):
        header, rows = local_rows()
        rows[1]["quat_s"] = "15"
        with self.assertRaises(ValueError):
            audit_csv_text(as_csv(header, rows))

    def test_wrong_headers_are_refused(self):
        header, rows = local_rows()
        header.remove("sclk")
        with self.assertRaises(ValueError):
            audit_csv_text(as_csv(header, [{k:v for k,v in r.items() if k != "sclk"}
                                             for r in rows]))


if __name__ == "__main__":
    unittest.main()
