"""Synthetic data for near-duplicate screening; NOT new physical measurements."""
import copy
import hashlib
import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]/"research"/"battery_curve_audit"
sys.path.insert(0,str(ROOT))
import near_duplicate_guard as g


def synthetic_trace(cell, *, noise=0., grid_step=1., spike=None, scale=1., flat=False):
    ts = [i*grid_step for i in range(round(160/grid_step)+1)]
    vs = [(3.0 if flat else 3.9 - 0.7*t/160 + 0.03*math.sin(t/22))*scale+noise for t in ts]
    if spike is not None:
        pos = min(range(len(ts)),key=lambda k:abs(ts[k]-spike))
        vs[pos] += .01
    return {"cell":cell,"mode":"dchg","run":1,"n":len(ts),"times":ts,
            "volts":vs,"trace_sha256":hashlib.sha256(cell.encode()).hexdigest()}


def sample_curves():
    return [{"cell":c,"mode":"dchg","run":1,"trace_sha256":hashlib.sha256(c.encode()).hexdigest()}
            for c in "ABCDE"]


class ScreeningTests(unittest.TestCase):
    def test_near_not_exact_on_resampled_grid(self):
        a=synthetic_trace("A",noise=0.,grid_step=1)
        b=synthetic_trace("B",noise=.0006,grid_step=.8)
        pair=g.compare_near(a,b)
        self.assertIsNotNone(pair)
        self.assertLess(pair["max_abs_voltage_diff_mv"],2)
        self.assertGreater(pair["comparison_knots"],150)

    def test_discrete_spike_cannot_hide_between_probes(self):
        a=synthetic_trace("A")
        b=synthetic_trace("B",noise=.0003,spike=73)
        self.assertIsNone(g.compare_near(a,b))

    def test_different_mode_and_flat_curve_rejected(self):
        a=synthetic_trace("A")
        b=synthetic_trace("B",noise=.0003)
        b["mode"]="chg"
        self.assertIsNone(g.compare_near(a,b))
        b["mode"]="dchg"
        b["volts"]=[3.2]*len(b["times"])
        self.assertIsNone(g.compare_near(a,b))

    def test_absolute_time_difference_is_not_warped_away(self):
        a=synthetic_trace("A")
        b=synthetic_trace("B",noise=.0005)
        b["times"]=[t+4 for t in b["times"]]
        self.assertIsNone(g.compare_near(a,b))

    def test_pairwise_transitive_groups_cross_cell(self):
        curves=sample_curves()
        candidates=[{"a":{"cell":"A"},"b":{"cell":"B"}},
                    {"a":{"cell":"B"},"b":{"cell":"C"}}]
        self.assertIn(["A","B","C"],g.components(curves,candidates))
        p=g.propose_split(curves,candidates)
        self.assertIsNotNone(p)
        self.assertEqual(g.verify_split(curves,candidates,p),p["partition_cell_counts"])
        ass={r["cell"]:r["partition"] for r in p["assignments"]}
        self.assertEqual(ass["A"],ass["C"])
        self.assertEqual(set(ass.values()),{"train","validation","test"})

    def test_missing_independent_groups_fail_closed(self):
        candidates=[{"a":{"cell":"A"},"b":{"cell":"B"}},
                    {"a":{"cell":"B"},"b":{"cell":"C"}},
                    {"a":{"cell":"C"},"b":{"cell":"D"}}]
        self.assertIsNone(g.propose_split(sample_curves(),candidates))

    def test_tampered_candidate_and_assignment_rejected(self):
        curves=sample_curves()
        candidates=[{"a":{"cell":"A"},"b":{"cell":"B"}}]
        original=g.propose_split(curves,candidates)
        tampered=copy.deepcopy(original)
        tampered["candidate_sha256"]="f"*64
        with self.assertRaisesRegex(ValueError,"candidate evidence mismatch"):
            g.verify_split(curves,candidates,tampered)
        tampered=copy.deepcopy(original)
        for row in tampered["assignments"]:
            if row["cell"]=="B":
                row["partition"]="validation" if row["partition"]!="validation" else "test"
        with self.assertRaisesRegex(ValueError,"near-candidate leakage"):
            g.verify_split(curves,candidates,tampered)

    def test_identical_hash_is_not_near_only(self):
        a=synthetic_trace("A")
        b=synthetic_trace("B",noise=.0003)
        b["trace_sha256"]=a["trace_sha256"]
        self.assertIsNone(g.compare_near(a,b))

    def test_source_csv_short_rows_preserved(self):
        raw=(b"Timestamp_1 [h],C1 [V],Timestamp_2 [h],C2 [V],Timestamp_3 [h],C3 [V]\n"
             b"0,3.8,0,3.9,0,4.0\n1,3.7,1,3.8\n2,3.6\n")
        traces=g.build_traces([(("chg","X","f"*40),raw)])
        self.assertEqual([r["n"] for r in traces],[3,2,1])
        self.assertEqual(traces[0]["volts"][-1],3.6)


if __name__=="__main__":
    unittest.main()
