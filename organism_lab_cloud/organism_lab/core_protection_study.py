"""Paired finite digital genome experiment for the #413 core-preservation hypothesis.

The parent world and its mutation draw mechanism remain unchanged. In the
protected variant, damaged COPY_REST and DIVIDE loci are restored *after* the
same RNG proposals have been drawn, so TASK_A/B proposals face the same four
alternative opcodes. This engineered protection is not autonomous AI learning.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from math import comb
import os
from pathlib import Path
import statistics
import tempfile

from .digital_vm import COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld, execute_genome

SCHEMA = 'cano-core-protection-paired-v1'
FOUNDER = (COPY_REST, TASK_A, DIVIDE)
ARMS = ('unrestricted', 'protected_core', 'no_mutation', 'no_division')


class CoreProtectedWorld(GenomeWorld):
    """Repair only structural loci in offspring; no reward or task targeting."""

    def _mutate(self, genome):
        candidate = super()._mutate(genome)
        if len(genome) != 3 or genome[0] != COPY_REST or genome[2] != DIVIDE:
            raise ValueError('Core-protection variant requires a viable three-locus founder lineage')
        return (genome[0], candidate[1], genome[2])


def _validate(seeds, steps, shift_tick, capacity, resources, mutation_rate, holdout_steps):
    if not isinstance(seeds, (tuple, list)) or not 20 <= len(seeds) <= 100:
        raise ValueError('Must use 20-100 unique paired seeds')
    if len(set(seeds)) != len(seeds) or any(type(s) is not int or s < 0 for s in seeds):
        raise ValueError('Invalid paired seeds')
    if type(steps) is not int or not 30 <= steps <= 300:
        raise ValueError('Steps must be between 30 and 300')
    if type(shift_tick) is not int or not 1 <= shift_tick < steps:
        raise ValueError('Shift must precede the final step')
    if type(capacity) is not int or not 2 <= capacity <= 64:
        raise ValueError('Capacity must be 2-64')
    if type(resources) is not int or not 0 <= resources <= 100:
        raise ValueError('Invalid tick resource budget')
    if type(mutation_rate) not in (int, float) or not 0 <= mutation_rate <= 1:
        raise ValueError('Invalid mutation rate')
    if type(holdout_steps) is not int or not 1 <= holdout_steps <= 50:
        raise ValueError('Invalid holdout steps')


def _viable_task_b(world):
    return sum(execute_genome(o.genome) is not None and TASK_B in o.genome for o in world.organisms)


def _trial(seed, arm, steps, shift_tick, capacity, resources, mutation_rate, holdout_steps):
    cls = CoreProtectedWorld if arm == 'protected_core' else GenomeWorld
    world = cls(seed=seed, capacity=capacity, resources_per_tick=resources,
                mutation_rate=0 if arm == 'no_mutation' else mutation_rate,
                initial_genome=FOUNDER, allow_replication=arm != 'no_division',
                environment=TASK_A, task_reward=2)
    for tick in range(1, steps + 1):
        if tick == shift_tick + 1:
            world.set_environment(TASK_B)
        world.step()
    final = world.metrics()
    functional = _viable_task_b(world)
    share = functional / final['population'] if final['population'] else 0.0
    reproducing = sum(execute_genome(o.genome) is not None for o in world.organisms)
    distinct = {tuple(o.genome) for o in world.organisms}
    # Counterfactual reward stress: same inherited genotypes, no fresh mutation.
    stress = deepcopy(world)
    stress.mutation_rate = 0.0
    stress.task_reward = 1
    for _ in range(holdout_steps):
        stress.step()
    stressed = stress.metrics()
    return {
        'seed': seed, 'arm': arm, 'final': final,
        'functional_b': functional, 'functional_b_share': share,
        'viable_replicator_share': reproducing / final['population'] if final['population'] else 0.0,
        'distinct_genomes': [list(g) for g in sorted(distinct)],
        'holdout_population': stressed['population'],
        'holdout_functional_b_share': (_viable_task_b(stress) / stressed['population']
                                      if stressed['population'] else 0.0),
    }


def _ci(values):
    mean = statistics.mean(values)
    d = 1.96 * statistics.stdev(values) / len(values)**0.5 if len(values)>1 else 0.0
    return {'mean': mean, 'ci95_low': mean-d, 'ci95_high': mean+d,
            'method': 'paired_normal_approximation', 'n': len(values)}


def _p_positive_nonzero(values):
    positive = sum(x > 0 for x in values)
    negative = sum(x < 0 for x in values)
    n = positive+negative
    return (sum(comb(n, k) for k in range(positive, n + 1)) / 2**n) if n else 1.0


def run_study(*, seeds=tuple(range(30)), steps=120, shift_tick=40,
              capacity=48, resources=1, mutation_rate=.08, holdout_steps=15):
    _validate(seeds, steps, shift_tick, capacity, resources, mutation_rate, holdout_steps)
    trials = [_trial(seed, arm, steps, shift_tick, capacity, resources,
                     mutation_rate, holdout_steps) for seed in seeds for arm in ARMS]
    groups = {arm: [t for t in trials if t['arm'] == arm] for arm in ARMS}
    def vals(arm, key):
        return [t[key] for t in groups[arm]]
    diffs = [a-b for a,b in zip(vals('protected_core','functional_b_share'),
                                 vals('unrestricted','functional_b_share'))]
    holdout_diffs = [a-b for a,b in zip(vals('protected_core','holdout_population'),
                                         vals('unrestricted','holdout_population'))]
    positives = sum(x>0 for x in diffs)
    negatives = sum(x<0 for x in diffs)
    b_p = _p_positive_nonzero(diffs)
    division_control_zero = all(x['final']['births']==0 for x in groups['no_division'])
    no_mutation_b_zero = all(x['functional_b']==0 for x in groups['no_mutation'])
    # Pre-declared, strict acceptance: avoid mistaking sparse wins for broad improvement.
    gate = (positives/len(seeds) >= .5 and b_p < .05 and _ci(diffs)['ci95_low'] > 0
            and _ci(holdout_diffs)['ci95_low'] >= 0 and division_control_zero
            and no_mutation_b_zero)
    summary = [{
        'arm': arm, 'mean_final_population': statistics.mean(t['final']['population'] for t in group),
        'mean_births': statistics.mean(t['final']['births'] for t in group),
        'mean_unique_genomes': statistics.mean(t['final']['unique_genomes'] for t in group),
        'functional_b_share': _ci(vals(arm, 'functional_b_share')),
        'viable_replicator_share': _ci(vals(arm, 'viable_replicator_share')),
        'holdout_population': _ci(vals(arm, 'holdout_population')),
        'holdout_functional_b_share': _ci(vals(arm, 'holdout_functional_b_share')),
    } for arm, group in groups.items()]
    return {
        'schema': SCHEMA,
        'design': {
            'seeds': list(seeds), 'steps': steps, 'shift_tick': shift_tick,
            'capacity': capacity, 'resources_per_tick': resources,
            'mutation_rate': float(mutation_rate), 'holdout_steps': holdout_steps,
            'founder_genome': list(FOUNDER), 'arms': list(ARMS),
            'environment': 'TASK_A for first shift_tick steps, then TASK_B',
            'treatment': 'Protected variant uses same point-mutation draws and alternatives but repairs structural loci at positions 0 and 2 of new offspring; unlike unrestricted, damaged core mutants cannot persist.',
            'primary_metric': 'paired final share of viable self-copying TASK_B carriers',
            'holdout': '15 steps with reduced B reward and frozen new mutation; not a novel task',
            'acceptance': '>=50% of ALL paired seeds with positive functional B improvement, one-sided exact sign p<0.05, normal-approximate 95% mean B difference lower bound>0, reduced-reward holdout population difference lower bound>=0, negative controls pass',
        },
        'summary': summary,
        'paired_functional_b_gain': _ci(diffs),
        'paired_holdout_population_gain': _ci(holdout_diffs),
        'positive_seeds': positives,
        'negative_seeds': negatives,
        'tied_seeds': len(diffs)-positives-negatives,
        'exact_one_sided_sign_p': b_p,
        'no_division_births_zero': division_control_zero,
        'no_mutation_functional_b_zero': no_mutation_b_zero,
        'robust_improvement_demonstrated': gate,
        'trials': trials,
        'limitations': [
            'Finite, deterministic toy simulation; no self-training LLM, physical or biological replication.',
            'Genome repair is engineered externally and is not an evolved mechanism.',
            'No truly novel TASK_C environment exists in the inherited simulator.',
            'Normal-approximation confidence interval describes seed variability only.',
            'Outcome of a pilot cannot be treated as prospectively preregistered external evidence.',
        ],
    }


def _encode(data):
    return (json.dumps(data,sort_keys=True,separators=(',', ':'),ensure_ascii=False)+'\n').encode('utf-8')


def verify_report(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data,dict) or set(data)!={'report','sha256'}:
        raise ValueError('Report shape invalid')
    if hashlib.sha256(_encode(data['report'])).hexdigest()!=data['sha256']:
        raise ValueError('Report digest mismatch')
    d=data['report']['design']
    rebuilt=run_study(seeds=d['seeds'],steps=d['steps'],shift_tick=d['shift_tick'],
                      capacity=d['capacity'],resources=d['resources_per_tick'],
                      mutation_rate=d['mutation_rate'],holdout_steps=d['holdout_steps'])
    if rebuilt!=data['report']:
        raise ValueError('Report deterministic recomputation mismatch')
    return data


def save_report(report,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    doc={'report':report,'sha256':hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        if verify_report(path)!=doc:
            raise FileExistsError('Destination already contains conflicting report')
        return doc
    fd,tmp=tempfile.mkstemp(prefix='.protected-core-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as fp:
            fp.write(_encode(doc));fp.flush();os.fsync(fp.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    verify_report(path)
    return doc


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seed-start',type=int,default=0)
    parser.add_argument('--seeds',type=int,default=30)
    args=parser.parse_args(argv)
    doc=save_report(run_study(seeds=tuple(range(args.seed_start,args.seed_start+args.seeds))),args.output)
    r=doc['report']
    print(json.dumps({'digest':doc['sha256'],'robust_improvement_demonstrated':r['robust_improvement_demonstrated'],'positive_seeds':r['positive_seeds'],'negative_seeds':r['negative_seeds'],'tied_seeds':r['tied_seeds'],'exact_one_sided_sign_p':r['exact_one_sided_sign_p']},sort_keys=True))
    return 0

if __name__=='__main__':
    raise SystemExit(main())