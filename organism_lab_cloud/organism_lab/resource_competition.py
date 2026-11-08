"""CANO Organism Lab: bounded competing-genotype test of selection opportunity.

This is a controlled mechanism experiment, NOT proof of evolved adaptation.
The original GenomeWorld is imported untouched. Three engineered genotypes
(A, B, A+B) start at equal abundance; no mutation ever takes place. Resource
ordering (oldest first vs rotating) and neutral capacity turnover (off/on)
form a 2x2 factorial design. A/B training environments alternate. Task rewards
are examined at costs 0,1,2 with paired zero-reward null controls.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from math import comb
from pathlib import Path
from random import Random
import statistics
import tempfile
import os

from .digital_vm import COPY_REST, DIVIDE, NOP, TASK_A, TASK_B, DigitalOrganism, GenomeWorld, execute_genome

SCHEMA = "cano-resource-competition-v1"
FOUNDER_GENOMES = {
    "A": (COPY_REST, TASK_A, NOP, DIVIDE),
    "B": (COPY_REST, NOP, TASK_B, DIVIDE),
    "AB": (COPY_REST, TASK_A, TASK_B, DIVIDE),
}
ARMS = ("seniority_closed", "rotation_closed", "seniority_turnover", "rotation_turnover")
COSTS = (0, 1, 2)


def classify(genome):
    return next((key for key, value in FOUNDER_GENOMES.items() if tuple(genome) == value), "OTHER")


class CompetitionWorld(GenomeWorld):
    """Frozen genotypes, neutral age rotation and neutral at-cap vacancy experiment.

    The altered allocation and turnover are external research interventions.
    Only this subclass overrides step; production VM stays unchanged.
    """
    def __init__(self, *, seed, allocation="seniority", turnover=False,
                 task_cost=0, task_reward=2, capacity=12, resources=1,
                 allow_replication=True):
        if allocation not in ("seniority", "rotation"):
            raise ValueError("unknown resource allocation policy")
        if type(turnover) is not bool or type(allow_replication) is not bool:
            raise ValueError("turnover and allow_replication must be booleans")
        if type(task_cost) is not int or not 0 <= task_cost <= 2:
            raise ValueError("task cost must be 0, 1 or 2")
        if type(task_reward) is not int or task_reward not in (0, 2):
            raise ValueError("only paired reward=0/2 is valid")
        if type(capacity) is not int or capacity != 12:
            raise ValueError("fixed capacity 12; do not optimize after observing data")
        if type(resources) is not int or resources != 1:
            raise ValueError("fixed resource=1; do not optimize after observing data")
        super().__init__(seed=seed,capacity=capacity,resources_per_tick=resources,
                         mutation_rate=0.0,initial_genome=FOUNDER_GENOMES["A"],
                         allow_replication=allow_replication,environment=TASK_A,
                         task_reward=task_reward)
        self.allocation = allocation
        self.turnover = turnover
        self.task_cost = task_cost
        self.reward_events = 0
        self.task_cost_spent = 0
        lineup = [key for key in FOUNDER_GENOMES for _ in range(4)]
        Random(seed+104729).shuffle(lineup) # independent from neutral turnover RNG
        self.organisms = [DigitalOrganism(i,None,0,4,FOUNDER_GENOMES[key])
                          for i,key in enumerate(lineup)]
        self.next_id = 12

    def step(self):
        self.tick += 1
        order = sorted(self.organisms,key=lambda o:o.identifier)
        if self.allocation == "rotation" and order:
            offset = (self.tick-1) % len(order)
            order = order[offset:] + order[:offset]
        available = self.resources_per_tick
        survivors = []
        for organism in order:
            energy = organism.energy - 1
            matched = self.environment in organism.genome
            if matched and self.task_reward:
                energy += self.task_reward-self.task_cost
                self.reward_events += 1
                self.task_cost_spent += self.task_cost
            gain = min(2,available)
            available -= gain
            energy += gain
            if energy > 0:
                survivors.append(DigitalOrganism(organism.identifier,organism.parent,
                                                 organism.generation,energy,organism.genome))
            else:
                self.deaths += 1
        if self.turnover and len(survivors)==self.capacity:
            # A phenotype-neutral death frees one vacancy at a full capacity.
            # RNG is seeded independently of genotype; no directed culling.
            victim = self.random.randrange(len(survivors))
            survivors.pop(victim)
            self.deaths += 1
        parents,children=[],[]
        for organism in survivors:
            child_genome = execute_genome(organism.genome) if self.allow_replication else None
            if (child_genome is not None and organism.energy >= 8
                and len(survivors)+len(children) < self.capacity):
                child = DigitalOrganism(self.next_id,organism.identifier,
                                        organism.generation+1,3,
                                        self._mutate(child_genome))
                children.append(child)
                self.next_id += 1
                self.births += 1
                organism = DigitalOrganism(organism.identifier,organism.parent,
                                           organism.generation,organism.energy-4,
                                           organism.genome)
            parents.append(organism)
        self.organisms = parents+children
        return self.metrics()


def _validate(seeds,steps,period):
    if not isinstance(seeds,(tuple,list)) or not 20<=len(seeds)<=60:
        raise ValueError("20-60 unique paired seeds required")
    if len(set(seeds))!=len(seeds) or any(type(s) is not int or s<0 for s in seeds):
        raise ValueError("seeds must be unique nonnegative integers")
    if type(steps) is not int or not 20<=steps<=120:
        raise ValueError("steps must be 20-120")
    if type(period) is not int or not 3<=period<=20:
        raise ValueError("period must be 3-20")


def trace_world(seed, arm, *, cost, reward, steps, period, allow_replication=True):
    if arm not in ARMS:
        raise ValueError("unknown arm")
    if type(steps) is not int or not 20<=steps<=120:
        raise ValueError("bad steps")
    if type(period) is not int or not 3<=period<=20:
        raise ValueError("bad period")
    allocation,turnover = arm.rsplit("_",1)
    world = CompetitionWorld(seed=seed,allocation=allocation,
                             turnover=(turnover=="turnover"),task_cost=cost,
                             task_reward=reward,allow_replication=allow_replication)
    initial={key:sum(classify(o.genome)==key for o in world.organisms)
             for key in FOUNDER_GENOMES}
    person_ticks=0
    ab_person_ticks=0
    first_birth=None
    capacity_ticks=0
    population_trace=[len(world.organisms)]
    for tick in range(1,steps+1):
        world.set_environment(TASK_A if ((tick-1)//period)%2==0 else TASK_B)
        world.step()
        if first_birth is None and world.births>0:
            first_birth=tick
        n=len(world.organisms)
        capacity_ticks += int(n==world.capacity)
        person_ticks += n
        ab_person_ticks += sum(classify(o.genome)=="AB" for o in world.organisms)
        population_trace.append(n)
        if n>world.capacity or n<0:
            raise AssertionError("capacity escaped")
    census={key:sum(classify(o.genome)==key for o in world.organisms)
            for key in FOUNDER_GENOMES}
    if sum(census.values())!=len(world.organisms):
        raise AssertionError("unrecognized or mutated genotype")
    return {"population":len(world.organisms),"genotype_counts":census,
            "initial_counts":initial,"ab_final_share":census['AB']/len(world.organisms) if world.organisms else 0.0,
            "person_ticks":person_ticks,"ab_person_ticks":ab_person_ticks,
            "first_birth":first_birth,"births":world.births,"deaths":world.deaths,
            "reward_events":world.reward_events,"task_cost_spent":world.task_cost_spent,
            "capacity_ticks":capacity_ticks,"population_trace":population_trace,
            "max_generation":world.metrics()['max_generation']}


def _ci(values):
    avg=statistics.mean(values)
    m=1.96*statistics.stdev(values)/(len(values)**.5) if len(values)>1 else 0
    return {"n":len(values),"mean":avg,"ci95_low":avg-m,"ci95_high":avg+m,
            "method":"normal_approx_paired_seed_description"}


def _p(vals):
    pos=sum(v>0 for v in vals)
    neg=sum(v<0 for v in vals)
    n=pos+neg
    return sum(comb(n,k) for k in range(pos,n+1))/2**n if n else 1.0


def run_competition(*,seeds=tuple(range(600,630)),steps=80,period=12):
    """Factorial paired fixed-group experiment, not spontaneous genome evolution."""
    _validate(seeds,steps,period)
    trials=[]
    for seed in seeds:
        for arm in ARMS:
            for cost in COSTS:
                active=trace_world(seed,arm,cost=cost,reward=2,steps=steps,period=period)
                null=trace_world(seed,arm,cost=cost,reward=0,steps=steps,period=period)
                trials.append({"seed":seed,"arm":arm,"cost":cost,
                               "active":active,"null":null,
                               "ab_share_causal":active['ab_final_share']-null['ab_final_share'],
                               "ab_person_ticks_causal":active['ab_person_ticks']-null['ab_person_ticks'],
                               "total_person_ticks_causal":active['person_ticks']-null['person_ticks'],
                               "births_causal":active['births']-null['births']})
    grouped={(t['seed'],t['cost'],t['arm']):t for t in trials}
    per_cost=[]
    for cost in COSTS:
        contrasts=[]
        rotation_effect=[]
        turnover_effect=[]
        for seed in seeds:
            r=grouped[seed,cost,'rotation_turnover']['ab_share_causal']
            baseline=grouped[seed,cost,'seniority_closed']['ab_share_causal']
            contrasts.append(r-baseline)
            rotation_effect.append(r-grouped[seed,cost,'seniority_turnover']['ab_share_causal'])
            turnover_effect.append(grouped[seed,cost,'seniority_turnover']['ab_share_causal']-baseline)
        positive=sum(v>0 for v in contrasts)
        negative=sum(v<0 for v in contrasts)
        per_cost.append({"task_cost":cost,"paired_joint_causal_ab_share":_ci(contrasts),
                         "rotation_effect_with_turnover":_ci(rotation_effect),
                         "turnover_effect_with_seniority":_ci(turnover_effect),
                         "positive_seeds":positive,"negative_seeds":negative,
                         "tied_seeds":len(seeds)-positive-negative,
                         "exact_sign_p_one_sided":_p(contrasts)})
    neutral=all(t['active']['population_trace']==t['null']['population_trace']
                and t['active']['genotype_counts']==t['null']['genotype_counts']
                and t['active']['births']==t['null']['births']
                for t in trials if t['cost']==2)
    same_founders=all(t['active']['initial_counts']=={'A':4,'B':4,'AB':4}
                      and t['null']['initial_counts']=={'A':4,'B':4,'AB':4} for t in trials)
    bounds=all(t['active']['population']<=12 and t['null']['population']<=12
               and t['active']['population']==12+t['active']['births']-t['active']['deaths']
               and t['null']['population']==12+t['null']['births']-t['null']['deaths'] for t in trials)
    no_division=all(trace_world(seed,'rotation_turnover',cost=0,reward=2,steps=steps,
                                period=period,allow_replication=False)['births']==0 for seed in seeds)
    primary=per_cost[0]
    # Predefined before computing results; does not permit post-hoc selecting cost 1/2.
    gate=(primary['positive_seeds']>=len(seeds)*0.5 and primary['exact_sign_p_one_sided']<.05
          and primary['paired_joint_causal_ab_share']['ci95_low']>0
          and neutral and same_founders and bounds and no_division)
    return {"schema":SCHEMA,"design":{
            "seeds":list(seeds),"steps":steps,"period":period,"capacity":12,"resources":1,
            "genotypes":{k:list(v) for k,v in FOUNDER_GENOMES.items()},
            "initial_allele_counts":{'A':4,'B':4,'AB':4},"mutation_rate":0,
            "arms":list(ARMS),"costs":list(COSTS),"reward":2,
            "schedule":"TASK_A/TASK_B alternating every period ticks, fixed in advance",
            "primary":"task_cost=0: (rotation+neutral-turnover reward-minus-null AB share) minus (seniority+closed reward-minus-null AB share)",
            "gate":">=50% of all seeds positive, exact one-sided sign p<0.05, paired descriptive 95% mean lower>0 in each independent cohort, neutral-zero-net and division-off controls pass",
            "limitation":"Initially seeded known A/B/AB genotypes; mechanism test not emergence or autonomous learning"},
            "per_cost":per_cost,"negative_controls":{
                "zero_net_reward_matches_null":neutral,
                "equal_founders":same_founders,"capacity_birth_death_conservation":bounds,
                "division_disabled_zero_births":no_division},
            "selection_mechanism_demonstrated":gate,
            "trials":trials,
            "limitations":["Engineered genotype mixture; A+B is seeded, not evolved.",
                           "Neutral turnover creates vacancies but is externally imposed and costs organism lives.",
                           "Combined primary policy changes both resource allocation and turnover; factorial contrasts disentangle parts.",
                           "Normal interval refers to fixed deterministic seeds, not external world inference.",
                           "Task cost 1 and 2 outcomes are predeclared sensitivity checks, not new primary claims.",
                           "No model training, physical robot, biology, network replication or production changes."]}


def _encode(obj):
    return (json.dumps(obj,sort_keys=True,separators=(',',':'),ensure_ascii=False)+'\n').encode('utf-8')


def save_report(report,path):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    payload={'report':report,'sha256':hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        if verify_report(path)!=payload:raise FileExistsError('Conflicting existing result')
        return payload
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.cano-competition-')
    try:
        with os.fdopen(fd,'wb') as w:
            w.write(_encode(payload));w.flush();os.fsync(w.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    verify_report(path)
    return payload


def verify_report(path):
    payload=json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload,dict) or set(payload)!={'report','sha256'}:
        raise ValueError('Malformed result')
    if hashlib.sha256(_encode(payload['report'])).hexdigest()!=payload['sha256']:
        raise ValueError('Digest mismatch')
    d=payload['report']['design']
    generated=run_competition(seeds=d['seeds'],steps=d['steps'],period=d['period'])
    if generated!=payload['report']:
        raise ValueError('Deterministic replay mismatch')
    return payload
