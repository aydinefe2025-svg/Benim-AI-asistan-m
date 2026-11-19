#!/usr/bin/env python3
"""CANO battery audit: fail-closed, cell-and-exact-curve group-aware split.

Input is original_20261118.py --output-json evidence (not raw customer data).
An identical curve creates an edge between its cells. Connected components
stay together across ALL charge/discharge runs, even with different cell IDs.
Distinct exact hashes do NOT prove scientific independence or no near-duplicates.
"""
import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

PARTITIONS = ("train", "validation", "test")
RATIOS = (0.6, 0.2, 0.2)
SCHEMA = "cano.battery.independent-holdout.v1"


def canonical_sha256(obj):
    payload = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def identities(audit):
    if not isinstance(audit, dict):
        raise ValueError("REVIEW_REQUIRED: audit must be an object")
    curves = audit.get("all_curve_identity")
    if not isinstance(curves, list) or not curves:
        raise ValueError("REVIEW_REQUIRED: missing all_curve_identity")
    if audit.get("trace_count") != len(curves):
        raise ValueError("REVIEW_REQUIRED: inconsistent trace_count")
    keys = set()
    digest_set = set()
    for c in curves:
        if not isinstance(c, dict):
            raise ValueError("REVIEW_REQUIRED: malformed curve")
        cell, mode, run, sha = (c.get(k) for k in ("cell", "mode", "run", "trace_sha256"))
        if (not isinstance(cell, str) or not cell or mode not in ("chg", "dchg")
                or not isinstance(run, int) or isinstance(run, bool) or run < 1
                or not isinstance(sha, str) or not re.fullmatch("[0-9a-f]{64}", sha)):
            raise ValueError("REVIEW_REQUIRED: invalid trace identity")
        ident = (cell, mode, run)
        if ident in keys:
            raise ValueError("REVIEW_REQUIRED: duplicate trace identity")
        keys.add(ident)
        digest_set.add(sha)
    if audit.get("unique_curve_count") != len(digest_set):
        raise ValueError("REVIEW_REQUIRED: inconsistent unique_curve_count")
    return curves


def cell_groups(curves):
    cells = sorted({c["cell"] for c in curves})
    parent = {cell: cell for cell in cells}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    same_sha_cells = defaultdict(set)
    for c in curves:
        same_sha_cells[c["trace_sha256"]].add(c["cell"])
    for members in same_sha_cells.values():
        ordered = sorted(members)
        for cell in ordered[1:]:
            union(ordered[0], cell)
    groups = defaultdict(list)
    for cell in cells:
        groups[find(cell)].append(cell)
    return sorted((sorted(v) for v in groups.values()), key=lambda g: (-len(g), g))


def create_manifest(audit, seed="cano-battery-v1"):
    curves = identities(audit)
    clusters = cell_groups(curves)
    if len(clusters) < 3:
        raise ValueError("REVIEW_REQUIRED: fewer than three independent cell groups")
    if not isinstance(seed, str) or not seed or len(seed) > 100:
        raise ValueError("REVIEW_REQUIRED: invalid seed")

    # Largest group is placed first; tie-breaking uses a fixed reproducible seed.
    clusters.sort(key=lambda g: (-len(g), canonical_sha256([seed, g])))
    targets = [max(1.0, len({c["cell"] for c in curves}) * r) for r in RATIOS]
    counts = {p: 0 for p in PARTITIONS}
    partition_for_cell = {}
    group_entries = []
    for group in clusters:
        p = min(range(3), key=lambda i: (counts[PARTITIONS[i]] / targets[i], counts[PARTITIONS[i]], i))
        name = PARTITIONS[p]
        counts[name] += len(group)
        for cell in group:
            partition_for_cell[cell] = name
        group_entries.append({
            "group_id": canonical_sha256(group)[:16],
            "cells": group,
            "partition": name,
        })
    assignments = [
        {"cell": c["cell"], "mode": c["mode"], "run": c["run"],
         "trace_sha256": c["trace_sha256"], "partition": partition_for_cell[c["cell"]]}
        for c in sorted(curves, key=lambda x: (x["cell"], x["mode"], x["run"]))
    ]
    manifest = {
        "schema": SCHEMA,
        "goal_key": "battery-20261119-cell-connected-exact-curve-holdout",
        "audit_sha256": canonical_sha256(audit),
        "seed": seed,
        "partition_cell_counts": counts,
        "independent_cell_group_count": len(clusters),
        "groups": sorted(group_entries, key=lambda x: x["group_id"]),
        "assignments": assignments,
        "limitations": [
            "Exact time-voltage equality only; near duplicates, shared batches and correlated experiments are not ruled out.",
            "No customer field validation, no model predictive accuracy or commercial validation.",
        ],
    }
    verify_manifest(audit, manifest)
    return manifest


def verify_manifest(audit, manifest):
    curves = identities(audit)
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ValueError("REVIEW_REQUIRED: unrecognized split schema")
    if manifest.get("audit_sha256") != canonical_sha256(audit):
        raise ValueError("REVIEW_REQUIRED: split does not match evidence SHA-256")
    assignments = manifest.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != len(curves):
        raise ValueError("REVIEW_REQUIRED: missing/extra assignments")
    seen = set()
    by_cell = defaultdict(set)
    by_sha = defaultdict(set)
    for c in assignments:
        if not isinstance(c, dict):
            raise ValueError("REVIEW_REQUIRED: invalid assignment")
        p = c.get("partition")
        if p not in PARTITIONS:
            raise ValueError("REVIEW_REQUIRED: unknown partition")
        key = (c.get("cell"), c.get("mode"), c.get("run"), c.get("trace_sha256"))
        if key in seen:
            raise ValueError("REVIEW_REQUIRED: repeated assignment")
        seen.add(key)
        by_cell[c["cell"]].add(p)
        by_sha[c["trace_sha256"]].add(p)
    expected = {(c["cell"], c["mode"], c["run"], c["trace_sha256"]) for c in curves}
    if seen != expected:
        raise ValueError("REVIEW_REQUIRED: identity/trace mismatch")
    if any(len(v) > 1 for v in by_cell.values()):
        raise ValueError("REVIEW_REQUIRED: same cell leaks across partitions")
    if any(len(v) > 1 for v in by_sha.values()):
        raise ValueError("REVIEW_REQUIRED: exact curve leaks across partitions")
    if {next(iter(v)) for v in by_cell.values()} != set(PARTITIONS):
        raise ValueError("REVIEW_REQUIRED: train/validation/test must all be nonempty")
    groups = manifest.get("groups")
    clusters = cell_groups(curves)
    actual_groups = sorted((tuple(x.get("cells", [])) for x in groups)) if isinstance(groups, list) else []
    if actual_groups != sorted(map(tuple, clusters)):
        raise ValueError("REVIEW_REQUIRED: split group graph was altered")
    for g in groups:
        if g.get("group_id") != canonical_sha256(g["cells"])[:16]:
            raise ValueError("REVIEW_REQUIRED: group ID altered")
        if any(g.get("partition") not in by_cell[cell] for cell in g["cells"]):
            raise ValueError("REVIEW_REQUIRED: group partition altered")
    counts = {p: sum(p in choices for choices in by_cell.values()) for p in PARTITIONS}
    if manifest.get("partition_cell_counts") != counts:
        raise ValueError("REVIEW_REQUIRED: count mismatch")
    if manifest.get("independent_cell_group_count") != len(clusters):
        raise ValueError("REVIEW_REQUIRED: group count mismatch")
    return counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audit-json", type=Path, required=True)
    ap.add_argument("--output-json", type=Path)
    ap.add_argument("--verify-json", type=Path)
    ap.add_argument("--seed", default="cano-battery-v1")
    a = ap.parse_args()
    audit = json.loads(a.audit_json.read_text(encoding="utf-8"))
    if a.verify_json:
        result = json.loads(a.verify_json.read_text(encoding="utf-8"))
        counts = verify_manifest(audit, result)
    else:
        result = create_manifest(audit, a.seed)
        counts = result["partition_cell_counts"]
        if a.output_json:
            a.output_json.parent.mkdir(parents=True, exist_ok=True)
            a.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ACCEPT: no exact-curve or same-cell train/validation/test leakage; cells=" +
          str(counts) + "; independent_groups=" + str(result["independent_cell_group_count"]))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("REVIEW_REQUIRED: " + str(exc), file=sys.stderr)
        sys.exit(2)
