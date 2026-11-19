#!/usr/bin/env python3
"""CANO: conservative, review-only near-duplicate detector and leakage-safe holdout.

Source: POLITEHNICA Bucharest / BulyK47/battery-datasets, DOI 10.21227/cm0f-jg66,
CC BY 4.0 (attribution required). No customer data or third-party uploads.

A near match is NOT proof of copying or physical dependence. This tool tests only
same-mode voltage traces whose absolute time endpoints nearly coincide. It
compares piecewise-linear interpolants at every original interior timestamp;
its max-voltage-distance threshold is a *screening rule*, not a learned cutoff.
Different-looking curves or off-grid traces may still be statistically related.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

import original_20261118 as original

PARTITIONS = ("train", "validation", "test")
SCHEMA = "cano.battery.near-curve-holdout.v1"
DEFAULT_TOLERANCE_MV = 2.0
DEFAULT_ENDPOINT_FRACTION = 0.005
DEFAULT_MIN_VOLTAGE_RANGE_V = 0.05
DEFAULT_MIN_POINTS = 100


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def build_traces(sources):
    """Sources: list of ((kind,cell,Git blob SHA), unaltered publisher bytes)."""
    traces = []
    for (kind, cell, pin), raw in sources:
        parsed = original.parse_six_columns(raw, kind=kind, file_name=f"{kind}_{cell}")
        for run, points in enumerate(parsed["traces"], 1):
            xy = [(float(t), float(v)) for t, v in points]
            trace_hash = hashlib.sha256("".join(t+"\t"+v+"\n" for t, v in points).encode()).hexdigest()
            traces.append({"cell": cell, "mode": kind, "run": run, "n": len(xy),
                           "times": [t for t, _ in xy], "volts": [v for _, v in xy],
                           "trace_sha256": trace_hash, "source_git_blob": pin})
    return sorted(traces, key=lambda x: (x["mode"], x["cell"], x["run"]))


def interpolate(times, volts, t):
    """Interpolate only inside measured time extent (no extrapolation)."""
    if t < times[0] or t > times[-1]:
        raise ValueError("REVIEW_REQUIRED: interpolation would extrapolate")
    k = bisect_right(times, t)
    if k == 0:
        return volts[0]
    if k >= len(times):
        return volts[-1]
    i = k - 1
    if times[i] == t:
        return volts[i]
    return volts[i] + (volts[i+1]-volts[i])*(t-times[i])/(times[i+1]-times[i])


def compare_near(a, b, *, tolerance_mv=DEFAULT_TOLERANCE_MV,
                 endpoint_fraction=DEFAULT_ENDPOINT_FRACTION,
                 min_voltage_range_v=DEFAULT_MIN_VOLTAGE_RANGE_V,
                 min_points=DEFAULT_MIN_POINTS):
    """Return candidate evidence or None. Requires same mode, nonflat signal and
    nearly matching *absolute* acquisition times. Not time-warp invariant.
    """
    if a["mode"] != b["mode"] or a["cell"] == b["cell"]:
        return None
    if a["trace_sha256"] == b["trace_sha256"]:
        return None  # Already protected by the exact-duplicate guard.
    if min(a["n"], b["n"]) < min_points:
        return None
    ta, tb, va, vb = a["times"], b["times"], a["volts"], b["volts"]
    da, db = ta[-1]-ta[0], tb[-1]-tb[0]
    if da <= 0 or db <= 0:
        raise ValueError("REVIEW_REQUIRED: invalid duration")
    extent = max(da, db)
    if (abs(ta[0]-tb[0]) > endpoint_fraction*extent
            or abs(ta[-1]-tb[-1]) > endpoint_fraction*extent):
        return None
    if (max(va)-min(va) < min_voltage_range_v
            or max(vb)-min(vb) < min_voltage_range_v):
        return None  # Flat traces are scientifically ambiguous: not auto-linked.
    start, stop = max(ta[0], tb[0]), min(ta[-1], tb[-1])
    if start >= stop:
        return None
    tol = tolerance_mv / 1000.0
    # Cheap necessary condition: no interpolation error may exceed threshold.
    for i in range(65):
        t = start + (stop-start)*i/64
        if abs(interpolate(ta, va, t)-interpolate(tb, vb, t)) > tol + 1e-12:
            return None
    # Sufficient condition: maxima of two piecewise-linear curves' absolute
    # difference occur at their union of knots (+ overlap boundaries).
    knots = sorted({start, stop, *(t for t in ta if start < t < stop),
                    *(t for t in tb if start < t < stop)})
    max_abs = max(abs(interpolate(ta, va, t)-interpolate(tb, vb, t)) for t in knots)
    if max_abs > tol + 1e-12:
        return None
    left, right = sorted((a, b), key=lambda x: (x["cell"], x["mode"], x["run"]))
    return {"a": {"cell": left["cell"], "mode": left["mode"], "run": left["run"]},
            "b": {"cell": right["cell"], "mode": right["mode"], "run": right["run"]},
            "max_abs_voltage_diff_mv": round(max_abs*1000, 9),
            "comparison_knots": len(knots), "duration_overlap_fraction": round((stop-start)/extent, 9),
            "classification": "NEAR_MATCH_REVIEW_ONLY"}


def candidates_for(traces, **options):
    by_mode = defaultdict(list)
    for item in traces:
        by_mode[item["mode"]].append(item)
    out = []
    for mode in sorted(by_mode):
        group = by_mode[mode]
        for i, a in enumerate(group):
            for b in group[i+1:]:
                match = compare_near(a, b, **options)
                if match is not None:
                    out.append(match)
    return out


def components(curves, near_candidates):
    """Union all trace-owning cells for both exact and near-match links."""
    cells = sorted({c["cell"] for c in curves})
    parents = {c: c for c in cells}
    def root(c):
        while parents[c] != c:
            parents[c] = parents[parents[c]]
            c = parents[c]
        return c
    def unite(a, b):
        ra, rb = root(a), root(b)
        if ra != rb:
            parents[max(ra,rb)] = min(ra,rb)
    same_sha = defaultdict(set)
    for c in curves:
        same_sha[c["trace_sha256"]].add(c["cell"])
    for members in same_sha.values():
        members = sorted(members)
        for other in members[1:]:
            unite(members[0], other)
    for candidate in near_candidates:
        a, b = candidate["a"]["cell"], candidate["b"]["cell"]
        if a not in parents or b not in parents:
            raise ValueError("REVIEW_REQUIRED: candidate references unknown cell")
        unite(a,b)
    grouped = defaultdict(list)
    for cell in cells:
        grouped[root(cell)].append(cell)
    return sorted((sorted(g) for g in grouped.values()), key=lambda g: (-len(g),g))


def propose_split(curves, near_candidates, seed="cano-battery-near-v1"):
    """Conservative candidate-linked atomic partition. No claim of physical independence."""
    if not isinstance(seed, str) or not 1 <= len(seed) <= 100:
        raise ValueError("REVIEW_REQUIRED: invalid seed")
    groups = components(curves, near_candidates)
    if len(groups) < 3:
        return None  # Cannot fabricate independent validation and test groups.
    groups.sort(key=lambda g: (-len(g), digest([seed,g])))
    n = sum(map(len,groups))
    ratios = (0.6, 0.2, 0.2)
    counts = dict.fromkeys(PARTITIONS, 0)
    by_cell, records = {}, []
    for g in groups:
        idx = min(range(3), key=lambda i: (counts[PARTITIONS[i]]/max(1.0,n*ratios[i]),
                                         counts[PARTITIONS[i]], i))
        partition = PARTITIONS[idx]
        counts[partition] += len(g)
        for c in g:
            by_cell[c] = partition
        records.append({"group_id": digest(g)[:16], "cells": g, "partition": partition})
    if not all(counts.values()):
        return None
    assignment = sorted(({"cell": c["cell"], "mode": c["mode"], "run": c["run"],
                          "trace_sha256": c["trace_sha256"], "partition": by_cell[c["cell"]]}
                         for c in curves), key=lambda a:(a["cell"],a["mode"],a["run"]))
    manifest = {"schema": SCHEMA, "seed": seed, "groups": records,
                "assignments": assignment, "partition_cell_counts": counts,
                "candidate_sha256": digest(near_candidates),
                "exact_and_candidate_connected_groups": len(groups)}
    verify_split(curves, near_candidates, manifest)
    return manifest


def verify_split(curves, near_candidates, manifest):
    """Independent reconstruction of group graph and all evidence identities."""
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("REVIEW_REQUIRED: invalid near-split schema")
    if manifest.get("candidate_sha256") != digest(near_candidates):
        raise ValueError("REVIEW_REQUIRED: candidate evidence mismatch")
    expected = {(c["cell"],c["mode"],c["run"],c["trace_sha256"]) for c in curves}
    actual, by_cell, by_sha = set(), defaultdict(set), defaultdict(set)
    rows = manifest.get("assignments")
    if not isinstance(rows, list) or len(rows) != len(curves):
        raise ValueError("REVIEW_REQUIRED: missing or extra assignments")
    for row in rows:
        if not isinstance(row, dict) or row.get("partition") not in PARTITIONS:
            raise ValueError("REVIEW_REQUIRED: invalid assignment partition")
        key = (row.get("cell"),row.get("mode"),row.get("run"),row.get("trace_sha256"))
        if key in actual:
            raise ValueError("REVIEW_REQUIRED: duplicate assignment")
        actual.add(key)
        by_cell[row["cell"]].add(row["partition"])
        by_sha[row["trace_sha256"]].add(row["partition"])
    if actual != expected:
        raise ValueError("REVIEW_REQUIRED: identity mismatch")
    if any(len(g)>1 for g in by_cell.values()) or any(len(g)>1 for g in by_sha.values()):
        raise ValueError("REVIEW_REQUIRED: exact leakage detected")
    for pair in near_candidates:
        a, b = pair["a"]["cell"], pair["b"]["cell"]
        if by_cell[a] != by_cell[b]:
            raise ValueError("REVIEW_REQUIRED: near-candidate leakage detected")
    expected_groups = components(curves, near_candidates)
    records = manifest.get("groups")
    if not isinstance(records, list) or sorted(tuple(r.get("cells",[])) for r in records) != sorted(map(tuple,expected_groups)):
        raise ValueError("REVIEW_REQUIRED: group graph altered")
    for r in records:
        if (r.get("group_id") != digest(r["cells"])[:16] or
                r.get("partition") not in PARTITIONS or
                any(by_cell[c] != {r["partition"]} for c in r["cells"])):
            raise ValueError("REVIEW_REQUIRED: group assignment altered")
    counts = {p: sum({p} == splits for splits in by_cell.values()) for p in PARTITIONS}
    if (not all(counts.values()) or manifest.get("partition_cell_counts") != counts
            or manifest.get("exact_and_candidate_connected_groups") != len(expected_groups)):
        raise ValueError("REVIEW_REQUIRED: split counts altered")
    return counts


def load_and_run(data_dir, audit_json, holdout_json, *, tolerance_mv=2.0,
                 endpoint_fraction=0.005, seed="cano-battery-near-v1"):
    if not math.isfinite(tolerance_mv) or not 0 < tolerance_mv <= 20:
        raise ValueError("REVIEW_REQUIRED: tolerance out of bounds (0,20] mV")
    if not math.isfinite(endpoint_fraction) or not 0 <= endpoint_fraction <= 0.02:
        raise ValueError("REVIEW_REQUIRED: endpoint fraction outside [0,0.02]")
    import independent_holdout  # Preserve existing exact-split verifier.
    audit = json.loads(Path(audit_json).read_text(encoding="utf-8"))
    legacy = json.loads(Path(holdout_json).read_text(encoding="utf-8"))
    independent_holdout.verify_manifest(audit, legacy)
    sources = [((kind, cell, original.PIN[kind][i]),
                original.fetch_original(Path(data_dir), kind, i, download=False))
               for kind in ("dchg", "chg") for i,cell in enumerate(original.SUFFIXES)]
    recalculated = original.make_evidence(sources)
    if digest(recalculated) != digest(audit):
        raise ValueError("REVIEW_REQUIRED: original source/audit evidence mismatch")
    traces = build_traces(sources)
    near = candidates_for(traces, tolerance_mv=tolerance_mv,
                          endpoint_fraction=endpoint_fraction)
    p_for_cell = {c["cell"]: c["partition"] for c in legacy["assignments"]}
    across = [pair for pair in near if p_for_cell[pair["a"]["cell"]] != p_for_cell[pair["b"]["cell"]]]
    proposal = propose_split(audit["all_curve_identity"], near, seed=seed)
    return {"schema": "cano.battery.near-screen.v1", "publisher": audit["publisher"],
            "source_audit_sha256": digest(audit), "legacy_holdout_sha256": digest(legacy),
            "scope": "60 published curves; same-mode nonflat absolute-time comparison",
            "thresholds": {"max_abs_voltage_difference_mv": tolerance_mv,
                           "max_endpoint_offset_fraction": endpoint_fraction,
                           "min_voltage_range_v": DEFAULT_MIN_VOLTAGE_RANGE_V,
                           "min_samples_per_curve": DEFAULT_MIN_POINTS},
            "near_candidate_count": len(near), "cross_legacy_holdout_count": len(across),
            "near_candidates": near, "cross_legacy_holdout_candidates": across,
            "proposed_near_safe_holdout": proposal,
            "decision": ("BLOCK_INSUFFICIENT_INDEPENDENT_GROUPS" if proposal is None
                         else "REVIEW_REQUIRED" if near else "PASS_SCREEN_ONLY"),
            "limitations": ["Near matches need human review and independent experimental provenance.",
                            "A negative screen cannot prove statistical independence or exclude different-time-grid leakage.",
                            "No validated SOH model, paid customer, or physical test."]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--audit-json", type=Path, required=True)
    ap.add_argument("--holdout-json", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--max-diff-mv", type=float, default=DEFAULT_TOLERANCE_MV)
    ap.add_argument("--endpoint-fraction", type=float, default=DEFAULT_ENDPOINT_FRACTION)
    ap.add_argument("--strict", action="store_true", help="Reject unresolved near candidates")
    args = ap.parse_args()
    try:
        evidence = load_and_run(args.data_dir, args.audit_json, args.holdout_json,
                                tolerance_mv=args.max_diff_mv,
                                endpoint_fraction=args.endpoint_fraction)
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(evidence, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
        print(f"{evidence['decision']}: near candidates={evidence['near_candidate_count']}, "
              f"cross legacy split={evidence['cross_legacy_holdout_count']}; JSON={args.output_json}")
        if args.strict and evidence["decision"] != "PASS_SCREEN_ONLY":
            return 2
        return 0
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print("REVIEW_REQUIRED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())