"""Bounded, prospectively specified fitness time-course and cap/resource sweep.

Research-only synthetic four-locus simulation. Reuses the original immutable
GenomeWorld and TaskGrammarWorld; does not change the live daily checkpoint.
A task bonus is compared against an otherwise identical zero-reward clone.
"""
from __future__ import annotations

from copy import deepcopy
from math import comb
from pathlib import Path
import argparse
import hashlib
import json
import os
import statistics
import tempfile

from .digital_vm import DigitalOrganism, GenomeWorld, TASK_A, TASK_B, execute_genome
from .compositional_transfer_study import FOUNDER, TaskGrammarWorld, novel_task_match

SCHEMA = 'cano-selection-pressure-sweep-v1'
PRIMARY_CAPACITY = 24
PRIMARY_RESOURCE = 1


def _validate_integer(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{name} must be an integer in [{lo},{hi}]')


def matched_snapshot(grammar, protected, *, max_individuals=12):
    """Matched surviving *counts*; sample actual genomes evenly by ID.

    This changes the population census and is a counterfactual assay, not a
    continuation of the original natural-population history. It cannot prove
    that the sampling preserves every rare genotype. Zero on either side yields
    two empty communities rather than artificially manufacturing organisms.
    """
    _validate_integer(max_individuals, 1, 64, 'max_individuals')
    n = min(max_individuals, len(grammar.organisms), len(protected.organisms))
    def sample(source):
        target = deepcopy(source)
        originals = sorted(source.organisms, key=lambda o: o.identifier)
        chosen = [originals[((2*i+1)*len(originals))//(2*n)] for i in range(n)] if n else []
        target.organisms = [DigitalOrganism(o.identifier, o.parent, o.generation, 3, o.genome)
                            for o in chosen]
        target.mutation_rate = 0.0
        return target
    return sample(grammar), sample(protected), n


def trace_composition(world, *, steps, reward, capacity, resources):
    """Trace the same reward-only update rule as existing holdout_composition.

    Recorded first division and population-person-ticks are diagnostic and do
    not purport to measure real biology or third-party agents.
    """
    _validate_integer(steps, 1, 50, 'steps')
    _validate_integer(reward, 0, 10, 'reward')
    _validate_integer(capacity, 1, 64, 'capacity')
    _validate_integer(resources, 0, 100, 'resources')
    if len(world.organisms) > capacity:
        raise ValueError('Do not silently truncate organisms when reducing capacity')
    clone = deepcopy(world)
    clone.capacity = capacity
    clone.resources_per_tick = resources
    clone.mutation_rate = 0.0
    clone.organisms = [DigitalOrganism(o.identifier, o.parent, o.generation, 3, o.genome)
                       for o in clone.organisms]
    starting_population = len(clone.organisms)
    first_division_tick = None
    cumulative_person_ticks = 0
    rewarded_events = 0
    trace = [starting_population]
    start_births = clone.births
    for t in range(1, steps+1):
        clone.tick += 1
        available = clone.resources_per_tick
        survivors = []
        for organism in sorted(clone.organisms, key=lambda o: o.identifier):
            energy = organism.energy - 1
            if novel_task_match(organism.genome):
                energy += reward
                if reward:
                    rewarded_events += 1
            gain = min(2, available)
            available -= gain
            energy += gain
            if energy > 0:
                survivors.append(DigitalOrganism(organism.identifier, organism.parent,
                                                 organism.generation, energy, organism.genome))
            else:
                clone.deaths += 1
        parents, children = [], []
        for organism in survivors:
            child_genome = execute_genome(organism.genome) if clone.allow_replication else None
            if (child_genome is not None and organism.energy >= 8
                and len(survivors)+len(children) < clone.capacity):
                children.append(DigitalOrganism(clone.next_id, organism.identifier,
                                                organism.generation+1, 3,
                                                clone._mutate(child_genome)))
                clone.next_id += 1
                clone.births += 1
                organism = DigitalOrganism(organism.identifier, organism.parent,
                                           organism.generation, organism.energy-4,
                                           organism.genome)
            parents.append(organism)
        clone.organisms = parents+children
        if children and first_division_tick is None:
            first_division_tick = t
        if not 0 <= len(clone.organisms) <= capacity:
            raise AssertionError('Population escaped hard capacity')
        trace.append(len(clone.organisms))
        cumulative_person_ticks += len(clone.organisms)
    return {
        'starting_population': starting_population,
        'population': len(clone.organisms),
        'person_ticks': cumulative_person_ticks,
        'births_added': clone.births-start_births,
        'first_division_tick': first_division_tick,
        'reward_events': rewarded_events,
        'novel_carriers': sum(novel_task_match(o.genome) for o in clone.organisms),
        'capacity_ticks': sum(pop==capacity for pop in trace[1:]),
        'population_trace': trace,
    }


def _train(seed, mode, *, steps, shift_tick, mutation_rate):
    if mode in ('task_grammar','core_protected'):
        world = TaskGrammarWorld(seed=seed,capacity=48,resources_per_tick=1,
                                 mutation_rate=mutation_rate,initial_genome=FOUNDER,
                                 allow_replication=True,environment=TASK_A,task_reward=2,
                                 mode=mode)
    else:
        world = GenomeWorld(seed=seed,capacity=48,resources_per_tick=1,
                            mutation_rate=0 if mode=='no_mutation' else mutation_rate,
                            initial_genome=FOUNDER,allow_replication=(mode!='no_division'),
                            environment=TASK_A,task_reward=2)
    for tick in range(1, steps+1):
        if tick==shift_tick+1:
            world.set_environment(TASK_B)
        world.step()
    return world


def _ci(numbers):
    mean = statistics.mean(numbers)
    margin = (1.96*statistics.stdev(numbers)/len(numbers)**.5) if len(numbers)>1 else 0.0
    return {'n':len(numbers),'mean':mean,'ci95_low':mean-margin,'ci95_high':mean+margin,
            'method':'descriptive_normal_approximation_fixed_paired_seeds'}


def _sign_p(vals):
    positive = sum(v>0 for v in vals)
    negative = sum(v<0 for v in vals)
    nonzero = positive+negative
    return (sum(comb(nonzero,k) for k in range(positive,nonzero+1))/2**nonzero) if nonzero else 1.0


def _validate_spec(seeds,steps,shift_tick,holdout_steps,capacities,resource_levels,sample_size,mutation_rate):
    if not isinstance(seeds,(list,tuple)) or not 20<=len(seeds)<=60 or any(type(s) is not int or s<0 for s in seeds) or len(set(seeds))!=len(seeds):
        raise ValueError('Provide 20-60 distinct nonnegative paired seeds')
    _validate_integer(steps,30,300,'steps')
    _validate_integer(shift_tick,1,steps-1,'shift_tick')
    _validate_integer(holdout_steps,1,50,'holdout_steps')
    _validate_integer(sample_size,1,12,'sample_size')
    for name,levels,lo,hi,primary in (('capacities',capacities,12,64,PRIMARY_CAPACITY),
                                      ('resources',resource_levels,0,100,PRIMARY_RESOURCE)):
        if not isinstance(levels,(tuple,list)) or not 2<=len(levels)<=3 or len(set(levels))!=len(levels):
            raise ValueError(f'{name} need 2-3 distinct levels')
        if any(type(v) is not int or not lo<=v<=hi for v in levels) or primary not in levels:
            raise ValueError(f'{name} must contain prespecified primary level')
    if type(mutation_rate) not in (float,int) or not 0<=mutation_rate<=1:
        raise ValueError('mutation_rate must be a bounded number')
    if sample_size>min(capacities):
        raise ValueError('Matched initial census cannot exceed the smallest capacity')


def run_pressure_sweep(*, seeds=tuple(range(300, 330)), steps=120, shift_tick=40,
                       holdout_steps=20, capacities=(12, 24, 48), resource_levels=(0, 1, 4),
                       sample_size=12, mutation_rate=0.08):
    """Compare C-reward causal lift under bounded fixed cap/resource pressures.

    Primary cell is (capacity 24, resources 1), fixed *before* outcomes. Other
    cells are sensitivity checks, not new independent confirmations. Never turn
    this assay into evidence of autonomous model-weight learning.
    """
    _validate_spec(seeds,steps,shift_tick,holdout_steps,capacities,resource_levels,
                   sample_size,mutation_rate)
    trials=[]
    controls=[]
    for seed in seeds:
        grammar = _train(seed,'task_grammar',steps=steps,shift_tick=shift_tick,mutation_rate=mutation_rate)
        core = _train(seed,'core_protected',steps=steps,shift_tick=shift_tick,mutation_rate=mutation_rate)
        no_mutation = _train(seed,'no_mutation',steps=steps,shift_tick=shift_tick,mutation_rate=mutation_rate)
        no_division = _train(seed,'no_division',steps=steps,shift_tick=shift_tick,mutation_rate=mutation_rate)
        controls.append({'seed':seed,'no_mutation_c_carriers':sum(novel_task_match(o.genome) for o in no_mutation.organisms),
                         'no_division_births':no_division.births})
        ga,co,n = matched_snapshot(grammar,core,max_individuals=sample_size)
        for cap in capacities:
            for res in resource_levels:
                gr = trace_composition(ga,steps=holdout_steps,reward=2,capacity=cap,resources=res)
                gn = trace_composition(ga,steps=holdout_steps,reward=0,capacity=cap,resources=res)
                cr = trace_composition(co,steps=holdout_steps,reward=2,capacity=cap,resources=res)
                cn = trace_composition(co,steps=holdout_steps,reward=0,capacity=cap,resources=res)
                grammar_lift=gr['person_ticks']-gn['person_ticks']
                core_lift=cr['person_ticks']-cn['person_ticks']
                row={'seed':seed,'capacity':cap,'resource':res,'matched_start_count':n,
                     'grammar':{'starting_population':n,'reward':gr,'null':gn},
                     'core':{'starting_population':n,'reward':cr,'null':cn},
                     'delta_person_ticks_causal':grammar_lift-core_lift,
                     'delta_births_causal':(gr['births_added']-gn['births_added'])-(cr['births_added']-cn['births_added']),
                     'delta_terminal_causal':(gr['population']-gn['population'])-(cr['population']-cn['population']),
                     'delta_reward_events':gr['reward_events']-cr['reward_events'],
                     'delta_population_rewarded':gr['population']-cr['population'],
                     'both_rewarded_at_cap':gr['population']==cr['population']==cap,
                     'both_rewarded_at_floor':gr['population']==cr['population']==1}
                trials.append(row)
    grid=[]
    for cap in capacities:
        for res in resource_levels:
            rows=[r for r in trials if r['capacity']==cap and r['resource']==res]
            diffs=[r['delta_person_ticks_causal'] for r in rows]
            births=[r['delta_births_causal'] for r in rows]
            terminal=[r['delta_terminal_causal'] for r in rows]
            positive=sum(x>0 for x in diffs)
            negative=sum(x<0 for x in diffs)
            grid.append({'capacity':cap,'resource':res,'paired_seeds':len(rows),
                         'positive_seeds':positive,'negative_seeds':negative,
                         'tied_seeds':len(rows)-positive-negative,
                         'sign_test_one_sided_p':_sign_p(diffs),
                         'paired_causal_person_ticks':_ci(diffs),
                         'paired_causal_births':_ci(births),
                         'paired_causal_terminal_population':_ci(terminal),
                         'rewarded_population_ties':sum(r['delta_population_rewarded']==0 for r in rows),
                         'both_rewarded_at_capacity':sum(r['both_rewarded_at_cap'] for r in rows),
                         'both_rewarded_at_floor':sum(r['both_rewarded_at_floor'] for r in rows),
                         'grammar_reward_first_division_count':sum(r['grammar']['reward']['first_division_tick'] is not None for r in rows),
                         'core_reward_first_division_count':sum(r['core']['reward']['first_division_tick'] is not None for r in rows),
                         'nonempty_matched_seeds':sum(r['matched_start_count']>0 for r in rows)})
    primary=next(x for x in grid if x['capacity']==PRIMARY_CAPACITY and x['resource']==PRIMARY_RESOURCE)
    neg_controls=all(x['no_division_births']==0 and x['no_mutation_c_carriers']==0 for x in controls)
    readback_controls=all(x['grammar']['null']['reward_events']==x['core']['null']['reward_events']==0 and
                          x['grammar']['starting_population']==x['core']['starting_population'] and
                          x['grammar']['reward']['population']<=x['capacity'] and
                          x['core']['reward']['population']<=x['capacity'] for x in trials)
    strict=(primary['positive_seeds']>=len(seeds)/2 and primary['sign_test_one_sided_p']<.05 and
            primary['paired_causal_person_ticks']['ci95_low']>0 and
            primary['paired_causal_births']['ci95_low']>=0 and neg_controls and readback_controls)
    return {'schema':SCHEMA,
            'design':{'seeds':list(seeds),'steps':steps,'shift_tick':shift_tick,'holdout_steps':holdout_steps,
                      'training_capacity':48,'training_resource':1,'sample_size':sample_size,
                      'capacities':list(capacities),'resource_levels':list(resource_levels),'mutation_rate':float(mutation_rate),
                      'primary':{'capacity':PRIMARY_CAPACITY,'resource':PRIMARY_RESOURCE},
                      'held_out_task':'reward C only if viable A and B; reward=2 versus matched reward=0; each start energy 3',
                      'sampling':'post-training matched source census=min(12, both alive); equispaced IDs, replacement forbidden; immutable source',
                      'primary_endpoint':'difference between grammar and protected in causal (reward minus no-reward) summed alive-person ticks at cap24 resource1',
                      'strict_acceptance':'in EACH independent seed cohort: >=50% all seeds positive primary paired causal time; one-sided sign p<.05; paired normal approximate 95% lower >0; paired causal births 95% lower >=0; all negative controls; otherwise FAIL',
                      'multiplicity':'remaining eight cap/resource cells are exploratory and do not reset primary gate'},
            'grid':grid,'trials':trials,'control_rows':controls,
            'controls':{'no_mutation_and_no_division_valid':neg_controls,
                        'null_reward_never_earns_task_bonus':all(r['grammar']['null']['reward_events']==r['core']['null']['reward_events']==0 for r in trials),
                        'paired_initial_population_equal':all(r['grammar']['starting_population']==r['core']['starting_population'] for r in trials),
                        'bounded_and_paired':readback_controls},
            'primary_strict_gate':strict,
            'adaptation_proven':False,
            'limits':['Synthetic timecourse simulation; no biological or AI model training result.',
                      'Matched post-training sample is a counterfactual; differences in rare genotypes may be lost by sampling.',
                      'C task is an engineered AND of trained A/B tasks; not independent real-world generalization.',
                      'CI describes finite deterministic seed selection only, not external validity.',
                      'Grid sensitivity is multiple-comparison exploratory; do not select a favorable cell after seeing results.',
                      'The primary gate tests an engineered metric in this simulation, not general intelligence.']}


def _encode(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8')


def save_report(report,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    doc={'report':report,'sha256':hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        verify_report(path)
        if json.loads(path.read_text(encoding='utf-8'))!=doc:
            raise FileExistsError('Conflicting existing report')
        return doc
    fd,scratch=tempfile.mkstemp(prefix='.pressure-sweep-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as out:
            out.write(_encode(doc));out.flush();os.fsync(out.fileno())
        os.replace(scratch,path)
    finally:
        if os.path.exists(scratch):os.unlink(scratch)
    verify_report(path)
    return doc


def verify_report(path):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(doc,dict) or set(doc)!={'report','sha256'}:
        raise ValueError('Malformed research report')
    report=doc['report']
    if hashlib.sha256(_encode(report)).hexdigest()!=doc['sha256']:
        raise ValueError('Report digest mismatch')
    d=report['design']
    expected=run_pressure_sweep(seeds=d['seeds'],steps=d['steps'],shift_tick=d['shift_tick'],
                                holdout_steps=d['holdout_steps'],capacities=d['capacities'],
                                resource_levels=d['resource_levels'],sample_size=d['sample_size'],
                                mutation_rate=d['mutation_rate'])
    if expected!=report:
        raise ValueError('Report recomputation mismatch')
    return doc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--seed-start',type=int,default=300)
    p.add_argument('--seed-count',type=int,default=30)
    args=p.parse_args(argv)
    report=run_pressure_sweep(seeds=tuple(range(args.seed_start,args.seed_start+args.seed_count)))
    doc=save_report(report,args.output)
    print(json.dumps({'verified':True,'sha256':doc['sha256'],'primary_strict_gate':report['primary_strict_gate'],
                      'primary':next(x for x in report['grid'] if x['capacity']==PRIMARY_CAPACITY and x['resource']==PRIMARY_RESOURCE)},sort_keys=True))
    return 0


if __name__=='__main__':
    main()
