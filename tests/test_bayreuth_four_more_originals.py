"""Fail-closed checks for the additional independent-source Bayreuth cohort."""
import hashlib
import json
import unittest
from research.battery_curve_audit import bayreuth_four_more_originals as m
from tests.test_bayreuth_additional_three_originals import synthetic_zip


def fake_manifest():
    ids = set(m.PRIOR_SOURCE_IDS) | set(m.NEW_ORIGINAL_MD5)
    n = 1
    while len(ids) < 48:
        ids.add(f"F{n:04d}")
        n += 1
    return {"id": int(m.core.RECORD_ID), "doi": m.core.RECORD_DOI,
            "files": [{"key": cell + ".zip", "checksum": "md5:" + m.NEW_ORIGINAL_MD5.get(cell, "0" * 32),
                       "size": 15_000_000} for cell in sorted(ids)]}


class TestFourNewPublisherOriginals(unittest.TestCase):
    def test_exact_four_official_cell_pins_do_not_overlap_five_previously_verified(self):
        self.assertEqual(len(m.NEW_ORIGINAL_MD5), 4)
        self.assertEqual(len(m.PRIOR_SOURCE_IDS), 5)
        self.assertFalse(set(m.NEW_ORIGINAL_MD5) & m.PRIOR_SOURCE_IDS)
        self.assertTrue(all(len(x) == 32 for x in m.NEW_ORIGINAL_MD5.values()))

    def test_publisher_source_identity_and_manifest_size(self):
        specs = m.verify_publisher_manifest(fake_manifest())
        self.assertEqual(set(specs), set(m.NEW_ORIGINAL_MD5))
        self.assertTrue(all(s["size"] == 15_000_000 for s in specs.values()))

    def test_missing_record_and_doi_are_rejected(self):
        d = fake_manifest()
        d["id"] = 10
        with self.assertRaisesRegex(ValueError, "identity"):
            m.verify_publisher_manifest(d)
        d = fake_manifest()
        d["doi"] = "10.5281/zenodo.0"
        with self.assertRaisesRegex(ValueError, "identity"):
            m.verify_publisher_manifest(d)

    def test_missing_or_corrupt_publisher_file_cannot_be_accepted(self):
        d = fake_manifest()
        d["files"] = [f for f in d["files"] if f["key"] != "F0003.zip"]
        with self.assertRaises(ValueError):
            m.verify_publisher_manifest(d)
        d = fake_manifest()
        next(f for f in d["files"] if f["key"] == "F0003.zip")["checksum"] = "md5:" + "0" * 32
        with self.assertRaisesRegex(ValueError, "checksum"):
            m.verify_publisher_manifest(d)

    def test_duplicate_and_short_cohort_cannot_be_accepted(self):
        d = fake_manifest()
        d["files"].append(d["files"][0])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            m.verify_publisher_manifest(d)
        d = fake_manifest()
        d["files"].pop()
        with self.assertRaisesRegex(ValueError, "48"):
            m.verify_publisher_manifest(d)

    def test_four_genuine_archive_structures_in_synthetic_fixture_only(self):
        blobs = {cell: synthetic_zip(cell) for cell in m.NEW_ORIGINAL_MD5}
        specs = {cell: {"size": len(blob), "md5": hashlib.md5(blob).hexdigest()}
                 for cell, blob in blobs.items()}
        # For this one fixture, use actual pinned MD5-free validator to check
        # source parsing and the physics arithmetic only; real-source pins
        # are exercised separately by official-manifest validation.
        r = m.analyze_four(blobs, specs, "0" * 64)
        self.assertEqual(r["new_independent_source_cell_count"], 4)
        self.assertEqual(r["distinct_original_cell_sources_after_past_and_this_audit"], 9)
        self.assertTrue(r["not_an_impact_resistance_measurement"])
        self.assertTrue(r["not_a_calibrated_absolute_capacity_loss"])
        self.assertTrue(r["does_not_generalize_to_all_48_cells"])
        self.assertEqual(r["matched_cell_counts"]["discharge"], 4)
        self.assertEqual(r["matched_cell_counts"]["charge"], 4)

    def test_partial_or_corrupt_inputs_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "all four"):
            m.analyze_four({}, {}, "0" * 64)
        blobs = {cell: synthetic_zip(cell) for cell in m.NEW_ORIGINAL_MD5}
        specs = {cell: {"size": len(blob), "md5": hashlib.md5(blob).hexdigest()}
                 for cell, blob in blobs.items()}
        specs["F0003"]["size"] += 1
        with self.assertRaisesRegex(ValueError, "byte-count"):
            m.analyze_four(blobs, specs, "0" * 64)

    def test_genuine_publisher_whitespace_header_layout_and_numeric_values(self):
        import io
        import zipfile
        header = "~Time[h] DataSet t-Step[h] t-Set[h] Line Command U[V] I[A] Ah[Ah] Ah-Step Wh[Wh] Cyc-Count State"
        rows = [
            "0.0 1 0.0 0.0 17 Discharge 4.20 -0.100 0.0 -0.0 0.0 1 1",
            "0.1 2 0.1 0.1 17 Discharge 3.80 -0.100 0.0 -0.01 0.0 1 1",
            "0.2 3 0.2 0.2 17 Discharge 3.00 -0.100 0.0 -0.02 0.0 1 1",
        ]
        buff = io.BytesIO()
        with zipfile.ZipFile(buff, "w") as z:
            z.writestr("F0003/M0001_checkup.txt",
                       "~Resultfile from Basytec Battery Test System\\n" +
                       header + "\\n" + "\\n".join(rows) + "\\n")
        buff.seek(0)
        with zipfile.ZipFile(buff) as z:
            x = list(m.core.native_rows(z, "F0003/M0001_checkup.txt"))
            check = m.core.scan_checkup(z, "F0003/M0001_checkup.txt")
        self.assertEqual(len(x), 3)
        self.assertEqual(x[1]["line"], "17")
        self.assertAlmostEqual(check["candidate_summary_by_command"]["discharge"][0]["integral_trapezoid_Ah"], 0.02)
        self.assertAlmostEqual(check["candidate_summary_by_command"]["discharge"][0]["source_peak_Ah_Step_abs_Ah"], 0.02)

    def test_no_fake_numeric_change_without_homologous_source_step(self):
        from unittest.mock import patch
        blobs = {cell: synthetic_zip(cell) for cell in m.NEW_ORIGINAL_MD5}
        specs = {cell: {"size": len(blob), "md5": hashlib.md5(blob).hexdigest()}
                 for cell, blob in blobs.items()}
        with patch.object(m.core, "infer_stage_line_offset",
                          return_value={"offset_inferred": False, "reason": "no valid matched protocol"}):
            r = m.analyze_four(blobs, specs, "0" * 64)
        self.assertEqual(r["matched_cell_counts"]["discharge"], 0)
        self.assertEqual(r["matched_cell_counts"]["charge"], 0)
        for cell in r["cells"].values():
            for phase in ("discharge", "charge"):
                self.assertFalse(cell["paired_measurement"][phase]["comparable"])
                self.assertNotIn("source_step_delta_mAh", cell["paired_measurement"][phase])


if __name__ == "__main__":
    unittest.main()
