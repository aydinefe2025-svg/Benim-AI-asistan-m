#!/usr/bin/env python3
"""Offline deterministic alias/negative-control challenge of reviewer identity gate.

All human IDs are synthetic. A distinct string is NOT proof of a distinct
human, external authority, independent review, laboratory truth or acceptance.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random

import field_pilot_evidence as field

SCHEMA = 'cano.battery.synthetic-reviewer-alias-lab.v1'
ALIAS_VARIANTS = (
    'lowercase', 'outer_padding', 'fullwidth_nfkc',
    'lowercase_fullwidth', 'invisible_format_reject', 'control_character_reject',
)
CONTROL_VARIANTS = (
    'underscore_not_hyphen', 'different_digit',
    'extra_suffix', 'different_prefix',
)


def fullwidth(text):
    return ''.join(chr(ord(ch) + 0xFEE0) if '!' <= ch <= '~' else ch for ch in text)


def fake_ledger(reviewer_a, reviewer_b):
    return {
        'schema': field.SCHEMA,
        'site_authorization': {'permitted': True, 'reference': 'FICTIONAL-NOT-A-SITE'},
        'audit_receipt_sha256': '0' * 64,
        'cells': [
            {'cell': c, 'device': 'DEV-' + c, 'batch': 'BATCH-' + c,
             'campaign': 'CAMP-' + c} for c in 'ABCD'
        ],
        'assignments': [
            {'cell': c, 'partition': part}
            for c, part in zip('ABCD', ('train', 'validation', 'test', 'train'))
        ],
        'screened_pair_count': 6,
        'screened_flagged_count': 0,
        'reviews': [
            {'a': 'A', 'b': 'B', 'flagged': False,
             'reviewer_a': {'id': reviewer_a, 'verdict': 'independent'},
             'reviewer_b': {'id': reviewer_b, 'verdict': 'independent'}}
        ],
    }


def alias(value, which):
    return {
        'lowercase': lambda s: s.lower(),
        'outer_padding': lambda s: '\u3000 ' + s + ' \u3000',
        'fullwidth_nfkc': fullwidth,
        'lowercase_fullwidth': lambda s: fullwidth(s.lower()),
        'invisible_format_reject': lambda s: s[:4] + '\u200b' + s[4:],
        'control_character_reject': lambda s: s + '\n',
    }[which](value)


def different(value, which):
    return {
        'underscore_not_hyphen': lambda s: s.replace('-', '_'),
        'different_digit': lambda s: s + '9',
        'extra_suffix': lambda s: s + '-ALT',
        'different_prefix': lambda s: 'OTHER-' + s,
    }[which](value)


def run_all(trials=100, seed=20261119):
    if type(trials) is not int or not (1 <= trials <= 1000):
        raise ValueError('REVIEW_REQUIRED: invalid trial count')
    if type(seed) is not int or not (0 <= seed < 2**32):
        raise ValueError('REVIEW_REQUIRED: invalid seed')
    rng = random.Random(seed)
    counts = Counter()
    def identifier():
        return 'TECH-' + ''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(9))
    for kind in ALIAS_VARIANTS:
        for _ in range(trials):
            raw = identifier()
            try:
                field.assess(fake_ledger(raw, alias(raw, kind)))
            except ValueError as exc:
                # Confirm rejection was reviewer-specific, not a setup error.
                if 'reviewer' not in str(exc):
                    raise AssertionError('Wrong rejection reason for synthetic reviewer alias') from exc
                counts['aliases_rejected'] += 1
            else:
                counts['aliases_escaped'] += 1
            counts['aliases_total'] += 1
    for kind in CONTROL_VARIANTS:
        for _ in range(trials):
            raw = identifier()
            report = field.assess(fake_ledger(raw, different(raw, kind)))
            if (report['decision'] != 'PILOT_METRICS_ONLY'
                    or report['consensus']['tn'] != 1
                    or report['field_acceptance'] != 'NOT_ESTABLISHED'):
                raise AssertionError('Unexpected synthetic distinct-identity control decision')
            counts['distinct_controls_not_rejected'] += 1
            counts['distinct_controls_total'] += 1
    result = {
        'schema': SCHEMA,
        'seed': seed,
        'trials_per_variant': trials,
        'total_cases': counts['aliases_total'] + counts['distinct_controls_total'],
        'alias_cases': counts['aliases_total'],
        'same_person_label_alias_rejected': counts['aliases_rejected'],
        'alias_escapes': counts['aliases_escaped'],
        'distinct_text_control_cases': counts['distinct_controls_total'],
        'distinct_text_controls_not_rejected': counts['distinct_controls_not_rejected'],
        'alias_transformations': list(ALIAS_VARIANTS),
        'different_text_controls': list(CONTROL_VARIANTS),
        'real_people_or_reviewers_identified': False,
        'reviewer_independence_cryptographically_verified': False,
        'field_false_positive_or_negative_rate_measured': False,
        'explanation': 'Matching canonical strings are blocked, different labels are not proof of separate persons or authorized signatures.',
    }
    if (result['alias_escapes'] or
            result['same_person_label_alias_rejected'] != result['alias_cases']):
        raise AssertionError('Safety gate missed a constructed reviewer identity alias')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trials', type=int, default=100)
    parser.add_argument('--seed', type=int, default=20261119)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    summary = run_all(args.trials, args.seed)
    if not args.output.parent.is_dir():
        raise ValueError('REVIEW_REQUIRED: output parent must already exist')
    data = (json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    fd = os.open(args.output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, 'wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    print('SYNTHETIC REVIEWER LAB PASS: ' + str(summary['total_cases']) +
          ' scenarios, aliases rejected=' + str(summary['same_person_label_alias_rejected']) +
          ' distinct-text controls=' + str(summary['distinct_text_controls_not_rejected']))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
