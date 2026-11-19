#!/usr/bin/env python3
"""Offline technician-adjudication and physical-provenance pilot gate.

Only evaluates *self-reported* instrument, batch and campaign provenance,
and reviewer consensus on a declared pairwise sampling frame. This code never
proves physically independent samples, unbiased labels, clinical/lab quality,
or real customer acceptance. No raw curve values or identifying site metadata
appear in the aggregate report. Python standard library only.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

SCHEMA = 'cano.battery.field-pilot.v1'
OUTPUT_SCHEMA = 'cano.battery.field-pilot-aggregate.v1'
PARTITIONS = frozenset(('train', 'validation', 'test'))
VERDICTS = frozenset(('linked', 'independent', 'unknown'))
MAX_BYTES = 1024 * 1024
MAX_CELLS = 1000
MAX_REVIEWS = 10000


def _named(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise ValueError('REVIEW_REQUIRED: invalid ' + label + ' metadata')
    return value


def _provenance_key(value, label):
    """Conservative grouping key, NOT an assertion of identical instruments.

    Preserve literal cell aliases and source identities elsewhere. Treat
    metadata differing only by Unicode compatibility, case or outer padding
    as a possible shared source that must not cross a train/test split.
    """
    name = _named(value, label)
    if any(unicodedata.category(c).startswith('C') for c in name):
        raise ValueError('REVIEW_REQUIRED: provenance control/format character in ' + label)
    return unicodedata.normalize('NFKC', name).strip().casefold()

def _strict_int(value, label, low=0, high=10_000_000):
    if not isinstance(value, int) or isinstance(value, bool) or value < low or value > high:
        raise ValueError('REVIEW_REQUIRED: invalid ' + label)
    return value


def _ratio(num, den):
    return round(num / den, 6) if den else None


def assess(ledger):
    """Return a privacy-minimal aggregate; never return identifying row data."""
    if not isinstance(ledger, dict) or ledger.get('schema') != SCHEMA:
        raise ValueError('REVIEW_REQUIRED: unsupported field-pilot schema')
    auth = ledger.get('site_authorization')
    if not isinstance(auth, dict) or auth.get('permitted') is not True:
        raise ValueError('REVIEW_REQUIRED: missing site authorization attestation')
    _named(auth.get('reference'), 'authorization reference')
    receipt = ledger.get('audit_receipt_sha256')
    if not isinstance(receipt, str) or re.fullmatch(r'[a-f0-9]{64}', receipt) is None:
        raise ValueError('REVIEW_REQUIRED: invalid audit receipt SHA-256')
    cells = ledger.get('cells')
    if not isinstance(cells, list) or not (3 <= len(cells) <= MAX_CELLS):
        raise ValueError('REVIEW_REQUIRED: expected 3..1000 cell metadata records')
    by_cell = {}
    for item in cells:
        if not isinstance(item, dict) or set(item) != {'cell', 'device', 'batch', 'campaign'}:
            raise ValueError('REVIEW_REQUIRED: incomplete cell device/batch/campaign metadata')
        alias = _named(item['cell'], 'cell')
        if alias in by_cell:
            raise ValueError('REVIEW_REQUIRED: duplicate cell identifier')
        by_cell[alias] = {name: _provenance_key(item[name], name) for name in ('device', 'batch', 'campaign')}
    assignments = ledger.get('assignments')
    if not isinstance(assignments, list) or len(assignments) != len(cells):
        raise ValueError('REVIEW_REQUIRED: missing or extra split assignments')
    partition_for = {}
    for item in assignments:
        if (not isinstance(item, dict) or set(item) != {'cell', 'partition'} or
                item['cell'] not in by_cell or item['partition'] not in PARTITIONS or
                item['cell'] in partition_for):
            raise ValueError('REVIEW_REQUIRED: malformed/duplicate split assignments')
        partition_for[item['cell']] = item['partition']
    if len(partition_for) != len(by_cell) or set(partition_for.values()) != PARTITIONS:
        raise ValueError('REVIEW_REQUIRED: split assignments must cover every cell and all three partitions')

    parent = {cell: cell for cell in by_cell}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(x, y):
        a, b = find(x), find(y)
        if a != b:
            parent[max(a, b)] = min(a, b)
    connected = set()
    metadata_edges = set()
    for kind in ('device', 'batch', 'campaign'):
        members = defaultdict(set)
        for cell, fields in by_cell.items():
            members[fields[kind]].add(cell)
        for group in members.values():
            group = sorted(group)
            for i in range(len(group)):
                for j in range(i+1, len(group)):
                    metadata_edges.add((group[i], group[j]))
            for cell in group[1:]:
                union(group[0], cell)
    cross_metadata = sum(partition_for[a] != partition_for[b] for a, b in metadata_edges)
    provenance_groups = len({find(c) for c in by_cell})

    total = _strict_int(ledger.get('screened_pair_count'), 'screened_pair_count', 1)
    flagged_total = _strict_int(ledger.get('screened_flagged_count'), 'screened_flagged_count')
    if total > len(cells) * (len(cells)-1) // 2 or flagged_total > total:
        raise ValueError('REVIEW_REQUIRED: impossible pair sampling frame')
    reviews = ledger.get('reviews')
    if not isinstance(reviews, list) or len(reviews) > min(total, MAX_REVIEWS):
        raise ValueError('REVIEW_REQUIRED: sampled review count exceeds declared pair frame')
    seen_pairs = set()
    flagged_reviewed = 0
    agree = {'tp': 0, 'fp': 0, 'fn': 0, 'tn': 0}
    disagreements = 0
    unresolved = 0
    technician_cross = 0
    for row in reviews:
        if not isinstance(row, dict) or set(row) != {'a', 'b', 'flagged', 'reviewer_a', 'reviewer_b'}:
            raise ValueError('REVIEW_REQUIRED: incomplete pair review')
        left, right = row['a'], row['b']
        if left not in by_cell or right not in by_cell or left == right:
            raise ValueError('REVIEW_REQUIRED: unknown or self-comparison cell pair')
        pair = tuple(sorted((left, right)))
        if pair in seen_pairs:
            raise ValueError('REVIEW_REQUIRED: duplicate unordered review pair')
        seen_pairs.add(pair)
        if type(row['flagged']) is not bool:
            raise ValueError('REVIEW_REQUIRED: flagged decision must be boolean')
        flagged_reviewed += row['flagged']
        reviewer_labels = []
        reviewer_ids = []
        for key in ('reviewer_a', 'reviewer_b'):
            reviewer = row[key]
            if not isinstance(reviewer, dict) or set(reviewer) != {'id', 'verdict'}:
                raise ValueError('REVIEW_REQUIRED: invalid reviewer record')
            reviewer_ids.append(_named(reviewer['id'], 'reviewer'))
            if reviewer['verdict'] not in VERDICTS:
                raise ValueError('REVIEW_REQUIRED: invalid reviewer verdict')
            reviewer_labels.append(reviewer['verdict'])
        if reviewer_ids[0] == reviewer_ids[1]:
            raise ValueError('REVIEW_REQUIRED: reviewer ids must differ')
        if 'unknown' in reviewer_labels:
            unresolved += 1
        elif reviewer_labels[0] != reviewer_labels[1]:
            disagreements += 1
        else:
            linked = reviewer_labels[0] == 'linked'
            slot = 'tp' if row['flagged'] and linked else ('fp' if row['flagged'] else ('fn' if linked else 'tn'))
            agree[slot] += 1
            if linked and partition_for[left] != partition_for[right]:
                technician_cross += 1
    clear_reviewed = len(reviews) - flagged_reviewed
    if flagged_reviewed > flagged_total or clear_reviewed > total - flagged_total:
        raise ValueError('REVIEW_REQUIRED: review count exceeds flagged/clear frame')
    if len(reviews) == total and flagged_reviewed != flagged_total:
        raise ValueError('REVIEW_REQUIRED: flagged frame count inconsistent with complete review')

    rates = {
        'precision': _ratio(agree['tp'], agree['tp'] + agree['fp']),
        'recall': _ratio(agree['tp'], agree['tp'] + agree['fn']),
        'specificity': _ratio(agree['tn'], agree['tn'] + agree['fp']),
        'false_positive_rate': _ratio(agree['fp'], agree['fp'] + agree['tn']),
        'false_negative_rate': _ratio(agree['fn'], agree['fn'] + agree['tp']),
    }
    safe_grouping = cross_metadata == 0 and provenance_groups >= 3
    if cross_metadata or technician_cross:
        decision = 'BLOCK_PROVENANCE_LEAKAGE'
    elif provenance_groups < 3:
        decision = 'BLOCK_INSUFFICIENT_PROVENANCE_GROUPS'
    else:
        decision = 'PILOT_METRICS_ONLY'
    return {
        'schema': OUTPUT_SCHEMA,
        'decision': decision,
        'field_acceptance': 'NOT_ESTABLISHED',
        'source_receipt_verified_from_raw_csv': False,
        'site_authorization_independently_verified': False,
        'provenance_independently_verified': False,
        'cell_count': len(cells),
        'provenance_connected_groups': provenance_groups,
        'provenance_group_holdout_valid': safe_grouping and technician_cross == 0,
        'cross_split_metadata_links': cross_metadata,
        'cross_split_technician_consensus_links': technician_cross,
        'screened_pair_count': total,
        'screened_flagged_count': flagged_total,
        'reviewed_pair_count': len(reviews),
        'full_frame_reviewed': len(reviews) == total and flagged_reviewed == flagged_total,
        'consensus_reviewed': sum(agree.values()),
        'disagreements': disagreements,
        'unresolved': unresolved,
        'consensus': agree,
        'rates': rates,
        'metric_denominators': {
            'precision': agree['tp'] + agree['fp'],
            'recall': agree['tp'] + agree['fn'],
            'specificity': agree['tn'] + agree['fp'],
        },
        'limitations': [
            'Reviewer consensus is a local annotation, not independently established ground truth.',
            'Metrics describe only adjudicated pairs in the declared sampling frame; incomplete/biased samples do not establish population error rates.',
            'A device/batch/campaign match is a conservative grouping rule, not proof of duplicate data.',
            'Provenance keys are conservatively NFKC/case/outer-whitespace matched; may review distinct case-sensitive serials.',
            'Source evidence and operator authorization are self-reported, not cryptographically/site independently verified.',
            'No field customer, financial willingness to pay, battery SOH model or accreditation validated.',
        ],
    }


def save_summary(ledger_path: Path, output_path: Path, summary):
    ledger_path = Path(ledger_path).resolve(strict=True)
    output_path = Path(output_path)
    target = output_path.resolve(strict=False)
    if target == ledger_path or output_path.exists() or output_path.is_symlink():
        raise ValueError('REVIEW_REQUIRED: cannot overwrite existing input or output')
    if not output_path.parent.is_dir():
        raise ValueError('REVIEW_REQUIRED: output parent does not exist')
    data = (json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    fd = os.open(output_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True, help='private field metadata and reviewer records')
    parser.add_argument('--summary', type=Path, required=True, help='privacy-minimal aggregate JSON')
    args = parser.parse_args(argv)
    try:
        if args.ledger.stat().st_size > MAX_BYTES:
            raise ValueError('REVIEW_REQUIRED: ledger exceeds 1MiB limit')
        ledger = json.loads(args.ledger.read_text(encoding='utf-8'))
        report = assess(ledger)
        save_summary(args.ledger, args.summary, report)
        print(f"{report['decision']}: reviewed={report['reviewed_pair_count']}; "
              f"consensus={report['consensus_reviewed']}; metadata_leaks={report['cross_split_metadata_links']}")
        return 2 if report['decision'].startswith('BLOCK_') else 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print('REVIEW_REQUIRED: ' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
