"""Regressions over real, pinned NASA PDS 3x3 DEM byte-range samples."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import unittest

from research.mars_dem_alignment import (
    CSV, LABEL, PATCHES, CHECK, audit_bundle, audit_pinned,
)


class MarsPdsRealDemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv_data = CSV.read_bytes()
        cls.dem_label = LABEL.read_bytes()
        cls.sampled = json.loads(PATCHES.read_text(encoding="utf-8"))
        cls.independent = json.loads(CHECK.read_text(encoding="utf-8"))

    def _mutate(self):
        return copy.deepcopy(self.sampled), copy.deepcopy(self.independent)

    @staticmethod
    def _resign(patches, check):
        digest = hashlib.sha256(json.dumps(
            patches["observations"], separators=(",", ":")).encode()).hexdigest()
        patches["observations_sha256"] = digest
        check["source_data_sha256"] = digest

    def _run(self, patches=None, check=None, csv_content=None, label=None):
        return audit_bundle(
            self.csv_data if csv_content is None else csv_content,
            self.dem_label if label is None else label,
            self.sampled if patches is None else patches,
            self.independent if check is None else check,
        )

    def test_real_full_source_and_independent_numerical_recomputation(self):
        result = audit_pinned()
        self.assertEqual(result["status"],
                         "offline_verified_real_pds_3x3_byte_range_samples")
        self.assertEqual(result["sample_count"], 577)
        self.assertEqual(result["metrics"]["dem_3x3_pixel_values"], 5193)
        self.assertEqual(result["metrics"]["unique_three_pixel_row_ranges"], 1681)

    def test_source_hashes_bind_to_actual_official_pds_data(self):
        self.assertEqual(hashlib.sha256(self.csv_data).hexdigest(),
                         "9da19e4f70287fe0d33ba716ff2169c10447c30c7a048583f730e4155226cde9")
        self.assertEqual(hashlib.sha256(self.dem_label).hexdigest(),
                         "7a736fabc434f4c6b4da17e0d943858809d10051570cc06570cb47f3c192e111")

    def test_real_elevation_residuals_and_local_gradient_counts(self):
        m = self._run()["metrics"]
        self.assertAlmostEqual(m["mean_absolute_height_difference_m"], 0.092969)
        self.assertAlmostEqual(m["median_absolute_height_difference_m"], 0.040477)
        self.assertAlmostEqual(m["p95_absolute_height_difference_m"], 0.236824)
        self.assertAlmostEqual(m["max_absolute_height_difference_m"], 3.993746)
        self.assertEqual(m["centers_over_1m_discrepancy"], 4)
        self.assertAlmostEqual(m["median_local_3x3_gradient_degrees"], 6.968824)
        self.assertEqual(m["local_3x3_gradients_over_15_degrees"], 65)

    def test_clustered_real_elevation_outliers_are_not_hidden(self):
        out = self._run()["outliers_gt_1m"]
        self.assertEqual([a["sol"] for a in out], [1347, 1348, 1349, 1351])
        self.assertEqual(set(a["site"] for a in out), {63})
        self.assertTrue(all(abs(a["delta_m"]) > 1 for a in out))

    def test_scientific_scope_flags_do_not_certify_terrain_or_life(self):
        result = self._run()
        self.assertFalse(result["full_binary_dem_verified"])
        self.assertFalse(result["vertical_unit_verified"])
        self.assertFalse(result["real_terrain_route_certified"])
        self.assertFalse(result["mars_life_found"])

    def test_repeatability_and_no_network_dependency(self):
        self.assertEqual(self._run(), self._run())

    def test_tampered_public_source_csv_is_rejected(self):
        bad = self.csv_data.replace(b"ROVER,3,28", b"ROVER,9,28", 1)
        self.assertNotEqual(bad, self.csv_data)
        with self.assertRaises(ValueError):
            self._run(csv_content=bad)

    def test_tampered_pds_raster_metadata_is_rejected(self):
        bad = self.dem_label.replace(b"IEEE754MSBSingle", b"IEEE754LSBSingle", 1)
        self.assertNotEqual(bad, self.dem_label)
        with self.assertRaises(ValueError):
            self._run(label=bad)

    def test_modified_dem_pixel_is_rejected_by_sha256(self):
        patches, check = self._mutate()
        patches["observations"][0][7][1][1] += 1.0
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_resigned_dem_pixel_is_rejected_by_independent_metrics(self):
        patches, check = self._mutate()
        patches["observations"][0][7][1][1] += 1.0
        self._resign(patches, check)
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_resigned_corrupted_raster_pixel_location_is_rejected(self):
        patches, check = self._mutate()
        patches["observations"][0][4] += 1
        self._resign(patches, check)
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_resigned_missing_three_by_three_row_is_rejected(self):
        patches, check = self._mutate()
        patches["observations"][0][7].pop()
        self._resign(patches, check)
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_resigned_nonfinite_numeric_pixel_is_rejected(self):
        patches, check = self._mutate()
        patches["observations"][0][7][1][1] = math.nan
        self._resign(patches, check)
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_resigned_false_rover_identity_is_rejected(self):
        patches, check = self._mutate()
        patches["observations"][0][0] += 1
        self._resign(patches, check)
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_incomplete_dataset_is_not_marked_verified(self):
        patches, check = self._mutate()
        patches["observations"].pop()
        self._resign(patches, check)
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_incorrect_raster_byte_range_size_is_rejected(self):
        patches, check = self._mutate()
        patches["provenance"]["dem_binary_size_verified_via_http_206"] -= 4
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_removed_no_flight_claim_is_rejected(self):
        patches, check = self._mutate()
        patches["provenance"]["no_real_rover_control"] = False
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_false_complete_raster_claim_is_rejected(self):
        patches, check = self._mutate()
        patches["provenance"]["not_a_full_DEM_copy"] = False
        with self.assertRaises(ValueError):
            self._run(patches, check)

    def test_wrong_independent_outlier_evidence_is_rejected(self):
        patches, check = self._mutate()
        check["outliers_abs_height_gt_1m"] = []
        with self.assertRaises(ValueError):
            self._run(patches, check)


if __name__ == "__main__":
    unittest.main()
