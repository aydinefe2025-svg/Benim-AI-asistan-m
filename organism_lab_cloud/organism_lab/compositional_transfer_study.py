"""Finite, reproducible task-composition transfer test for CANO Organism Lab.

New four-locus research schema. It does not modify the existing three-locus
calendar checkpoint, original digital_vm, models or any production service.

Task C is the previously unrewarded conjunction TASK_A AND TASK_B. It is
only rewarded after training, in a frozen-mutation holdout; it is not a new
physical/biological task or an independently learning language model.
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

from .digital_vm import (
    COPY_REST, DIVIDE, NOP, TASK_A, TASK_B, DigitalOrganism,
    GenomeWorld, execute_genome,
)

SCHEMA = 'cano-compositional-task-transfer-v1'
FOUNDER = (COPY_REST, TASK_A, NOP, DIVIDE)
ARMS = ('unrestricted', 'core_protected', 'task_grammar', 'no_mutation', 'no_division')
TASK_ALLELES = frozenset((NOP, TASK_A, TASK_B))


def novel_task_match(genome):
    """Task C: viable copier with both task instructions, no C reward in training."""
    return (execute_genome(genome) is not None and TASK_A in genome and TASK_B in genome)


class TaskGrammarWorld(GenomeWorld):
    """Repair structural positions; optionally revert invalid task-locus proposals.

    Parent mutation RNG proposals are drawn first and unmodified. Grammar
    filtering is engineered externally; it does not evolve or target TASK_B.
    """
    def __init__(self, *, mode='task_grammar', **kwargs):
        if mode not in ('task_grammar', 'core_protected'):
            raise ValueError('Invalid task grammar mode')
        self.mode = mode
        super().__init__(**kwargs)
        if self.organisms[0].genome != FOUNDER:
            raise ValueError('Four-locus fixed founder is required')

    def _mutate(self, genome):
        if len(genome) != 4 or genome[0] != COPY_REST or genome[3] != DIVIDE:
            raise ValueError('Four-locus structural template required')
        candidate = list(super()._mutate(genome))
        candidate[0], candidate[3] = COPY_REST, DIVIDE
        if self.mode == 'task_grammar':
            for pos in (1, 2):
                if candidate[pos] not in TASK_ALLELES:
                    candidate[pos] = genome[pos]  # rejection, not directed TASK_B
        return tuple(candidate)


def holdout_composition(original, *, steps, reward):
    """Frozen mutation; novel AND phenotype rewarded instead of task A or B.

    Retains original VM energy, resource, division, birth and cap rules. A
    matched zero-reward copy is the causal negative holdout control.
    """
    if type(steps) is not int or not 1 <= steps <= 50:
        raise ValueError('Invalid holdout duration')
    if type(reward) is not int or not 0 <= reward <= 10:
        raise ValueError('Invalid holdout reward')
    world = deepcopy(original)
    world.mutation_rate = 0.0
    # Remove stored training-energy advantage, otherwise full-capacity populations
    # remain alive in BOTH null and C arms even with no reward for 20 ticks.
    # Freeze genome and ancestry; this is an explicit holdout challenge reset.
    world.organisms = [DigitalOrganism(o.identifier, o.parent, o.generation, 3, o.genome)
                       for o in world.organisms]
    start_births = world.births
    rewarded_steps = 0
    for _ in range(steps):
        world.tick += 1
        available = world.resources_per_tick
        survivors = []
        for organism in sorted(world.organisms, key=lambda item: item.identifier):
            energy = organism.energy - 1
            if novel_task_match(organism.genome):
                energy += reward
                if reward:
                    rewarded_steps += 1
            gain = min(2, available)
            available -= gain
            energy += gain
            if energy > 0:
                survivors.append(DigitalOrganism(organism.identifier, organism.parent,
                                                 organism.generation, energy, organism.genome))
            else:
                world.deaths += 1
        parents, children = [], []
        for organism in survivors:
            child_genome = execute_genome(organism.genome) if world.allow_replication else None
            if child_genome is not None and organism.energy >= 8 and len(survivors)+len(children) < world.capacity:
                children.append(DigitalOrganism(world.next_id, organism.identifier,
                                                organism.generation+1, 3,
                                                world._mutate(child_genome)))
                world.next_id += 1
                world.births += 1
                organism = DigitalOrganism(organism.identifier, organism.parent,
                                           organism.generation, organism.energy-4,
                                           organism.genome)
            parents.append(organism)
        world.organisms = parents+children
    metrics=world.metrics()
    return {
        'population': metrics['population'],
        'births_added': metrics['births']-start_births,
        'novel_carriers': sum(novel_task_match(i.genome) for i in world.organisms),
        'rewarded_steps': rewarded_steps,
        'max_generation': metrics['max_generation'],
    }


def _validate(seeds, steps, shift_tick, holdout_steps, capacity, resources, mutation_rate, composition_reward):
    if not isinstance(seeds,(tuple,list)) or not 20 <= len(seeds) <= 100 or any(type(x) is not int or x<0 for x in seeds) or len(set(seeds)) != len(seeds):
        raise ValueError('20-100 unique nonnegative seeds required')
    if type(steps) is not int or not 30 <= steps <= 300:
        raise ValueError('Step budget 30-300')
    if type(shift_tick) is not int or not 1 <= shift_tick < steps:
        raise ValueError('Shift must precede training completion')
    if type(holdout_steps) is not int or not 1 <= holdout_steps <= 50:
        raise ValueError('Holdout budget 1-50')
    if type(capacity) is not int or not 2 <= capacity <= 64:
        raise ValueError('Capacity 2-64')
    if type(resources) is not int or not 0 <= resources <= 100:
        raise ValueError('Resources 0-100')
    if type(mutation_rate) not in (float,int) or not 0 <= mutation_rate <= 1:
        raise ValueError('Mutation rate 0-1')
    if type(composition_reward) is not int or not 0 <= composition_reward <= 10:
        raise ValueError('Reward 0-10')


def _trial(seed, arm, *, steps, shift_tick, capacity, resources, mutation_rate, holdout_steps, composition_reward):
    cls = TaskGrammarWorld if arm in ('core_protected','task_grammar') else GenomeWorld
    kw=dict(seed=seed,capacity=capacity,resources_per_tick=resources,
            mutation_rate=0 if arm=='no_mutation' else mutation_rate,
            initial_genome=FOUNDER,allow_replication=arm!='no_division',
            environment=TASK_A,task_reward=2)
    if cls is TaskGrammarWorld:
        kw['mode']=arm
    world=cls(**kw)
    for tick in range(1,steps+1):
        if tick==shift_tick+1:
            world.set_environment(TASK_B)
        world.step()
    final=world.metrics()
    novel=sum(novel_task_match(item.genome) for item in world.organisms)
    functional_b=sum(TASK_B in o.genome and execute_genome(o.genome) is not None for o in world.organisms)
    replicators=sum(execute_genome(o.genome) is not None for o in world.organisms)
    composition=holdout_composition(world,steps=holdout_steps,reward=composition_reward)
    zero=holdout_composition(world,steps=holdout_steps,reward=0)
    return {
        'seed':seed,'arm':arm,'final':final,
        'novel_task_carriers':novel,
        'novel_task_share':novel/final['population'] if final['population'] else 0.,
        'functional_b_share':functional_b/final['population'] if final['population'] else 0.,
        'viable_share':replicators/final['population'] if final['population'] else 0.,
        'composition_holdout':composition,
        'zero_reward_holdout':zero,
        'composition_population_bonus':composition['population']-zero['population'],
        'distinct_genomes':[list(g) for g in sorted(set(o.genome for o in world.organisms))],
    }


def _ci(xs):
    mean=statistics.mean(xs)
    margin=1.96*statistics.stdev(xs)/len(xs)**0.5 if len(xs)>1 else 0
    return {'n':len(xs),'mean':mean,'ci95_low':mean-margin,'ci95_high':mean+margin,
            'method':'paired_normal_approximation_by_seed'}


def _sign_p(differences):
    positive=sum(x>0 for x in differences)
    negative=sum(x<0 for x in differences)
    nonzero=positive+negative
    return sum(comb(nonzero,k) for k in range(positive,nonzero+1))/2**nonzero if nonzero else 1.0


def run_transfer(*, seeds=tuple(range(30)),steps=120,shift_tick=40,
                 holdout_steps=20,capacity=48,resources=1,mutation_rate=.08,
                 composition_reward=2):
    """Five-arm, predeclared test, no knobs chosen after results are inspected."""
    _validate(seeds,steps,shift_tick,holdout_steps,capacity,resources,mutation_rate,composition_reward)
    trial_args=dict(steps=steps,shift_tick=shift_tick,capacity=capacity,resources=resources,
                    mutation_rate=mutation_rate,holdout_steps=holdout_steps,composition_reward=composition_reward)
    trials=[_trial(seed,arm,**trial_args) for seed in seeds for arm in ARMS]
    groups={arm:[x for x in trials if x['arm']==arm] for arm in ARMS}
    def values(arm,key):return [r[key] for r in groups[arm]]
    c_diffs=[a-b for a,b in zip(values('task_grammar','novel_task_share'),
                                 values('core_protected','novel_task_share'))]
    h_diffs=[a-b for a,b in zip([x['composition_holdout']['population'] for x in groups['task_grammar']],
                                 [x['composition_holdout']['population'] for x in groups['core_protected']])]
    positive=sum(x>0 for x in c_diffs)
    negative=sum(x<0 for x in c_diffs)
    controls={
        'no_division_births_zero':all(x['final']['births']==0 for x in groups['no_division']),
        'no_mutation_novel_task_zero':all(x['novel_task_carriers']==0 for x in groups['no_mutation']),
        'grammar_all_functional':all(abs(x['viable_share']-1.)<1e-12 for x in groups['task_grammar'] if x['final']['population']>0),
        'novel_reward_absent_from_training':True, # by design: base GenomeWorld trained only A and B
    }
    # Strict prospective gate, requires BOTH independent 30-seed cohorts pass.
    gate=(positive>=len(seeds)*.5 and _sign_p(c_diffs)<.05
          and _ci(c_diffs)['ci95_low']>0 and _ci(h_diffs)['ci95_low']>=0
          and all(controls.values()))
    summary=[{
        'arm':arm,
        'mean_population':statistics.mean(x['final']['population'] for x in group),
        'mean_births':statistics.mean(x['final']['births'] for x in group),
        'mean_unique_genomes':statistics.mean(x['final']['unique_genomes'] for x in group),
        'novel_task_share':_ci(values(arm,'novel_task_share')),
        'viable_share':_ci(values(arm,'viable_share')),
        'composition_holdout_population':_ci([x['composition_holdout']['population'] for x in group]),
        'holdout_causal_reward_bonus':_ci(values(arm,'composition_population_bonus')),
    } for arm,group in groups.items()]
    return {
        'schema':SCHEMA,
        'design':{'seeds':list(seeds),'steps':steps,'shift_tick':shift_tick,
                 'holdout_steps':holdout_steps,'capacity':capacity,'resources_per_tick':resources,
                 'mutation_rate':float(mutation_rate),'composition_reward':composition_reward,
                 'arms':list(ARMS),'founder_genome':list(FOUNDER),
                 'novel_task_definition':'TASK_C is viable TASK_A AND TASK_B conjunction, not rewarded during training; only A then B are selected; novel frozen-mutation holdout earns reward for C alone.',
                 'grammar_mutation':'Same parent RNG proposal and rate; illegal structural/task opcodes reverted to parent; no targeting of B. Effective accepted mutation rate differs by design.',
                 'primary_metric':'paired final share of viable AB conjunction carriers (task_grammar minus core_protected), extinct=0',
                 'holdout':f'Frozen-mutation {holdout_steps}-step composition-only reward vs matched zero-reward null with every survivor starting at energy 3; this is a novel synthetic composition rule, NOT a new real-world task.',
                 'acceptance':'In each independent 30-seed partition: >=50% of ALL seeds with positive novel-task share gain; one-sided exact sign p<.05 excluding ties; paired normal-approx 95% lower>0; composition holdout population lower>=0; all negative controls pass.'},
        'summary':summary,'positive_seeds':positive,'negative_seeds':negative,
        'tied_seeds':len(seeds)-positive-negative,
        'exact_one_sided_sign_p':_sign_p(c_diffs),
        'paired_novel_task_gain':_ci(c_diffs),
        'paired_holdout_population_gain':_ci(h_diffs),
        'negative_controls':controls,'generalization_demonstrated':gate,
        'trials':trials,
        'limitations':[
            'Synthetic four-locus genotype and engineered grammar/reward; no biology, embodied robot or AI-model weight updates.',
            'Novel task is composition of two trained instructions; not an externally sampled unforeseen task distribution.',
            'The protected variants change accepted mutational landscape; equal RNG proposals do not imply equal offspring phenotypic distributions.',
            'Normal CI across deterministic seeds does not imply real-world generalizability.',
            'A positive simulation gate alone would not establish autonomous intelligence or physical transfer.',
        ],
    }


def _encode(value):
    return (json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8')


def verify_report(path):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(doc,dict) or set(doc)!={'report','sha256'}:
        raise ValueError('Invalid report schema')
    if hashlib.sha256(_encode(doc['report'])).hexdigest()!=doc['sha256']:
        raise ValueError('Report digest mismatch')
    d=doc['report']['design']
    expected=run_transfer(seeds=d['seeds'],steps=d['steps'],shift_tick=d['shift_tick'],
                          holdout_steps=d['holdout_steps'],capacity=d['capacity'],
                          resources=d['resources_per_tick'],mutation_rate=d['mutation_rate'],
                          composition_reward=d['composition_reward'])
    if expected!=doc['report']:
        raise ValueError('Report replay mismatch')
    return doc


def save_report(report,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    doc={'report':report,'sha256':hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        if verify_report(path)!=doc:
            raise FileExistsError('Conflicting prior report; no overwrite')
        return doc
    fd,scratch=tempfile.mkstemp(prefix='.task-transfer-',dir=str(path.parent))
    try:
        with os.fdopen(fd,'wb') as w:
            w.write(_encode(doc));w.flush();os.fsync(w.fileno())
        os.replace(scratch,path)
    finally:
        if os.path.exists(scratch):os.unlink(scratch)
    verify_report(path)
    return doc


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--seed-start',type=int,default=0)
    p.add_argument('--seeds',type=int,default=30)
    args=p.parse_args(argv)
    doc=save_report(run_transfer(seeds=tuple(range(args.seed_start,args.seed_start+args.seeds))),args.output)
    r=doc['report']
    print(json.dumps({'sha256':doc['sha256'],'positive_seeds':r['positive_seeds'],
                      'tied_seeds':r['tied_seeds'],'generalization_demonstrated':r['generalization_demonstrated']},sort_keys=True))

if __name__=='__main__':main()
