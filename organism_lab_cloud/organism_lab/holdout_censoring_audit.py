"""Read-only forensic of the 2026-11-08 CANO synthetic composition holdout.

This is *retrospective*: it analyzes 450 existing simulator runs (90 paired seeds),
not a new simulation or proof of biological/agent learning.  It quantifies a
measurement ceiling/floor and the tradeoff between task exposure and births.
The three independently pinned report digests are GitHub-era evidence anchors,
not signatures.  The report's SHA-256 alone cannot authenticate its origin.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import tempfile

SCHEMA = 'cano-holdout-censoring-forensic-v1'
SOURCE_SCHEMA = 'cano-compositional-task-transfer-v1'
EXPECTED_BODY_SHA256 = {
    'energy-reset-seeds-0-29.json': '17a6141db8949e30aaccc335bf3010c5e91b2d17a18b97f379c7ca29741e1ec8',
    'energy-reset-seeds-100-129.json': '8f20ceba1d3c9bf83a6220e83bc95c8307a74461923bd00a7465ccfccd89d526',
    'forward-test-seeds-200-229.json': '54230779ada3d306f06c915129f84c1012dfff24d0538b2421db22367ac50d59',
}
ARMS = ('unrestricted', 'core_protected', 'task_grammar', 'no_mutation', 'no_division')


def _encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def verify_archived_report(path, *, check_pins=True):
    """Check embedded digest, pinned original digest, design and row grain."""
    path = Path(path)
    document = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or set(document) != {'report', 'sha256'}:
        raise ValueError('Malformed stored report')
    report = document['report']
    if not isinstance(report, dict) or report.get('schema') != SOURCE_SCHEMA:
        raise ValueError('Unknown source report schema')
    digest = hashlib.sha256(_encode(report)).hexdigest()
    if digest != document['sha256']:
        raise ValueError('Report digest mismatch')
    if check_pins and digest != EXPECTED_BODY_SHA256.get(path.name):
        raise ValueError('Report differs from pinned source hash')
    design = report.get('design')
    if not isinstance(design, dict) or design.get('arms') != list(ARMS):
        raise ValueError('Invalid study arms')
    seeds = design.get('seeds')
    if not isinstance(seeds, list) or len(seeds) != 30 or len(set(seeds)) != 30 or any(type(x) is not int or x < 0 for x in seeds):
        raise ValueError('Invalid 30-seed cohort')
    trials = report.get('trials')
    if not isinstance(trials, list) or len(trials) != 150:
        raise ValueError('Invalid 150-row cohort')
    pairs = {}
    cap = design.get('capacity')
    if type(cap) is not int or not 2 <= cap <= 64:
        raise ValueError('Invalid population cap')
    for trial in trials:
        if not isinstance(trial, dict):
            raise ValueError('Malformed trial')
        seed, arm = trial.get('seed'), trial.get('arm')
        if seed not in seeds or arm not in ARMS:
            raise ValueError('Unexpected seed/arm')
        group = pairs.setdefault(seed, {})
        if arm in group:
            raise ValueError('Duplicate seed/arm')
        group[arm] = trial
        final, holdout, null = trial['final'], trial['composition_holdout'], trial['zero_reward_holdout']
        if not 0 <= final['population'] <= cap or final['population'] != 1 + final['births'] - final['deaths']:
            raise ValueError('Invalid final population accounting')
        if not 0 <= holdout['population'] <= cap or not 0 <= null['population'] <= cap:
            raise ValueError('Out-of-bounds holdout population')
        if not 0 <= trial['novel_task_share'] <= 1:
            raise ValueError('Out-of-range carrier share')
        if arm == 'no_division' and final['births'] != 0:
            raise ValueError('Division-disabled control produced births')
        if arm == 'no_mutation' and trial['novel_task_carriers'] != 0:
            raise ValueError('Mutation-disabled control produced novel task')
    if set(pairs) != set(seeds) or any(set(groups) != set(ARMS) for groups in pairs.values()):
        raise ValueError('Missing controls or seed/arm imbalance')
    return report, digest, pairs


def _mean_ci(values):
    average = statistics.mean(values)
    m = 1.96 * statistics.stdev(values) / len(values) ** .5 if len(values) > 1 else 0.0
    return {'mean': average, 'ci95_low': average-m, 'ci95_high': average+m,
            'n': len(values), 'method': 'descriptive_normal_approximation_on_fixed_paired_seeds'}


def _metrics(rows):
    return {
        'pairs': len(rows),
        'final_population_ties': sum(r['population_delta'] == 0 for r in rows),
        'both_at_capacity': sum(r['both_at_capacity'] for r in rows),
        'both_at_floor': sum(r['both_at_floor'] for r in rows),
        'other_ties': sum(r['population_delta'] == 0 and not r['both_at_capacity'] and not r['both_at_floor'] for r in rows),
        'task_share_gain_hidden_by_population_tie': sum(r['task_share_delta'] > 0 and r['population_delta'] == 0 for r in rows),
        'positive_task_share': sum(r['task_share_delta'] > 0 for r in rows),
        'negative_task_share': sum(r['task_share_delta'] < 0 for r in rows),
        'tied_task_share': sum(r['task_share_delta'] == 0 for r in rows),
        'rewarded_step_delta': _mean_ci([r['rewarded_step_delta'] for r in rows]),
        'births_added_delta': _mean_ci([r['births_added_delta'] for r in rows]),
        'final_population_delta': _mean_ci([r['population_delta'] for r in rows]),
        'task_share_delta': _mean_ci([r['task_share_delta'] for r in rows]),
    }


def audit_reports(paths, *, check_pins=True):
    paths = list(map(Path, paths))
    if len(paths) != 3 or len(set(p.name for p in paths)) != 3 or set(p.name for p in paths) != set(EXPECTED_BODY_SHA256):
        raise ValueError('Require the three exact distinct historical cohorts')
    # Stable chronological grouping independent of directory/glob order.
    paths = sorted(paths, key=lambda p: tuple(EXPECTED_BODY_SHA256).index(p.name))
    cohort_stats = []
    all_rows = []
    hashes = {}
    all_seeds = set()
    for path in paths:
        report, digest, pairs = verify_archived_report(path, check_pins=check_pins)
        hashes[path.name] = digest
        if all_seeds.intersection(pairs):
            raise ValueError('Seed overlap between cohorts')
        all_seeds.update(pairs)
        cap = report['design']['capacity']
        cohort_rows = []
        for seed, grouped in sorted(pairs.items()):
            grammar = grouped['task_grammar']
            protected = grouped['core_protected']
            gh, ph = grammar['composition_holdout'], protected['composition_holdout']
            gn, pn = grammar['zero_reward_holdout'], protected['zero_reward_holdout']
            if gn['population'] != pn['population']:
                raise ValueError('Null-reward source control mismatch')
            row = {
                'cohort': path.name,
                'seed': seed,
                'task_share_delta': grammar['novel_task_share'] - protected['novel_task_share'],
                'population_delta': gh['population'] - ph['population'],
                'rewarded_step_delta': gh['rewarded_steps'] - ph['rewarded_steps'],
                'births_added_delta': gh['births_added'] - ph['births_added'],
                'both_at_capacity': gh['population'] == ph['population'] == cap,
                'both_at_floor': gh['population'] == ph['population'] == 1,
                'task_grammar_population': gh['population'],
                'core_protected_population': ph['population'],
            }
            cohort_rows.append(row)
        cohort_stats.append({'file': path.name, **_metrics(cohort_rows)})
        all_rows.extend(cohort_rows)
    pooled = _metrics(all_rows)
    if pooled['final_population_ties'] < pooled['both_at_capacity'] + pooled['both_at_floor']:
        raise ValueError('Inconsistent floor/ceiling accounting')
    return {
        'schema': SCHEMA,
        'classification': 'posthoc_forensic_not_new_experiment',
        'paired_seeds': len(all_rows),
        'source_simulations': 5 * len(all_rows),
        'input_body_sha256': hashes,
        'cohorts': cohort_stats,
        'pooled': pooled,
        'per_seed': all_rows,
        'adaptation_proven': False,
        'interpretation': (
            'Posthoc ceiling/floor measurement diagnosis, not an intervention or new adaptation proof. '
            'Final population ties commonly occur at a shared cap or one-survivor floor. '
            'Task exposures and later births are distinct, sometimes opposed metrics. '
            'This evidence cannot prove that saturation is the only causal mechanism; '
            'a new prospectively designed time-course/capacity intervention is needed.'
        ),
    }


def save_audit(report, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {'report': report, 'sha256': hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        prior = json.loads(path.read_text(encoding='utf-8'))
        if prior != doc:
            raise FileExistsError('Conflicting existing audit')
        return doc
    fd, tmp = tempfile.mkstemp(prefix='.cano-audit-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as w:
            w.write(_encode(doc));w.flush();os.fsync(w.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    if json.loads(path.read_text(encoding='utf-8')) != doc:
        raise ValueError('Audit readback mismatch')
    return doc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    paths = [args.source_dir / name for name in EXPECTED_BODY_SHA256]
    data = audit_reports(paths)
    saved = save_audit(data, args.output)
    print(json.dumps({'saved': str(args.output), 'sha256': saved['sha256'],
                      'paired_seeds': data['paired_seeds'], 'pooled': data['pooled'],
                      'adaptation_proven': False}, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
