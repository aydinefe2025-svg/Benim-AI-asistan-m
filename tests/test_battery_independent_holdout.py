"""Synthetic regression tests. They do not claim a real-data rerun."""
import copy
import hashlib
import importlib.util
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "research" / "battery_curve_audit"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load("holdout", "independent_holdout.py")
original = load("original_battery", "original_20261118.py")


def sha(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def synthetic_audit():
    curves = []
    for cell in ("A", "B", "C", "D", "E", "F"):
        for mode in ("chg", "dchg"):
            for run in (1, 2, 3):
                fingerprint = cell + "-" + mode + "-" + str(run)
                if cell in ("A", "B") and mode == "dchg" and run == 1:
                    fingerprint = "SHARED-AB-DC1"
                curves.append({
                    "cell": cell, "mode": mode, "run": run,
                    "trace_sha256": sha(fingerprint),
                    "n": 20, "source_git_blob": "a" * 40,
                })
    return {
        "trace_count": len(curves),
        "unique_curve_count": len({c["trace_sha256"] for c in curves}),
        "all_curve_identity": curves,
    }


class BatteryLeakageTests(unittest.TestCase):
    def test_duplicate_cells_are_atomic(self):
        evidence = synthetic_audit()
        manifest = guard.create_manifest(evidence)
        self.assertEqual(guard.verify_manifest(evidence, manifest),
                         manifest["partition_cell_counts"])
        assignments = manifest["assignments"]
        p = {r["cell"]: r["partition"] for r in assignments}
        self.assertEqual(p["A"], p["B"])
        self.assertEqual(set(p.values()), {"train", "validation", "test"})
        self.assertEqual(manifest["independent_cell_group_count"], 5)

    def test_repeatable_split(self):
        audit = synthetic_audit()
        self.assertEqual(guard.create_manifest(audit),
                         guard.create_manifest(audit))

    def test_cross_partition_duplicate_fails_closed(self):
        audit = synthetic_audit()
        manifest = guard.create_manifest(audit)
        other = "test" if manifest["assignments"][0]["partition"] != "test" else "train"
        for assignment in manifest["assignments"]:
            if assignment["cell"] == "B":
                assignment["partition"] = other
        with self.assertRaisesRegex(ValueError, "leaks across partitions"):
            guard.verify_manifest(audit, manifest)

    def test_single_cell_leak_fails_closed(self):
        audit = synthetic_audit()
        manifest = guard.create_manifest(audit)
        first = manifest["assignments"][0]
        first["partition"] = "test" if first["partition"] != "test" else "train"
        with self.assertRaisesRegex(ValueError, "same cell leaks"):
            guard.verify_manifest(audit, manifest)

    def test_tampered_evidence_or_id_is_rejected(self):
        audit = synthetic_audit()
        m = guard.create_manifest(audit)
        another = copy.deepcopy(audit)
        another["all_curve_identity"][0]["trace_sha256"] = sha("tampered")
        with self.assertRaisesRegex(ValueError, "evidence SHA"):
            guard.verify_manifest(another, m)
        m["groups"][0]["group_id"] = "changed"
        with self.assertRaisesRegex(ValueError, "group ID"):
            guard.verify_manifest(audit, m)

    def test_missing_duplicated_and_malformed_identities(self):
        audit = synthetic_audit()
        audit["trace_count"] += 1
        with self.assertRaisesRegex(ValueError, "trace_count"):
            guard.create_manifest(audit)
        audit = synthetic_audit()
        audit["all_curve_identity"][1]["trace_sha256"] = "xyz"
        with self.assertRaisesRegex(ValueError, "trace identity"):
            guard.create_manifest(audit)
        audit = synthetic_audit()
        audit["all_curve_identity"][1] = copy.deepcopy(audit["all_curve_identity"][0])
        with self.assertRaisesRegex(ValueError, "duplicate trace identity"):
            guard.create_manifest(audit)

    def test_three_partitions_need_independent_groups(self):
        audit = synthetic_audit()
        audit["all_curve_identity"] = [c for c in audit["all_curve_identity"]
                                       if c["cell"] in {"A", "B", "C"}]
        audit["trace_count"] = len(audit["all_curve_identity"])
        audit["unique_curve_count"] = len({c["trace_sha256"] for c in audit["all_curve_identity"]})
        # A+B together, C alone means only 2 groups.
        with self.assertRaisesRegex(ValueError, "fewer than three"):
            guard.create_manifest(audit)

    def test_valid_short_charge_fields_not_zero_filled(self):
        fixture = (b"Timestamp_1 [h],C1 [V],Timestamp_2 [h],C2 [V],Timestamp_3 [h],C3 [V]\n"
                   b"0,3.3,0,3.2,0,3.1\n"
                   b"1,3.4,1,3.3\n"
                   b"2,3.5\n")
        p = original.parse_six_columns(fixture, kind="chg", file_name="fixture")
        self.assertEqual(p["width_counts"], {6: 1, 4: 1, 2: 1})
        self.assertEqual([len(x) for x in p["traces"]], [3, 2, 1])
        self.assertEqual(p["traces"][0][-1], ("2", "3.5"))
        with self.assertRaisesRegex(ValueError, "unexpected discharge short"):
            original.parse_six_columns(fixture, kind="dchg", file_name="fixture")

    def test_missing_voltage_and_nonmonotonic_time_are_rejected(self):
        h = b"Timestamp_1 [h],C1 [V],Timestamp_2 [h],C2 [V],Timestamp_3 [h],C3 [V]\n"
        with self.assertRaisesRegex(ValueError, "incomplete"):
            original.parse_six_columns(h+b"0,3.3,0,3.2,0,3.1\n1,\n",
                                       kind="chg", file_name="fixture")
        with self.assertRaisesRegex(ValueError, "nonincreasing"):
            original.parse_six_columns(h+b"0,3.3,0,3.2,0,3.1\n0,3.4,1,3.3,1,3.2\n",
                                       kind="chg", file_name="fixture")


if __name__ == "__main__":
    unittest.main()
