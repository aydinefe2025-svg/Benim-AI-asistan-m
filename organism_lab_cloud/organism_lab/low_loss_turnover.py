"""Bounded, prospective low-loss vacancy experiment in a 12-slot digital sandbox.

This study changes only a research-only subclass of a previously validated
CompetitionWorld. The founder genotypes A, B, AB are *engineered* into the
initial population, mutations are zero, and an improved policy is not an
adaptive AI or biological organism. The intervention is vacancy cadence and
eligibility, not targeted mutation, cloning or external replication.
"""
from __future__ import annotations

import hashlib
import json
import os
import statistics
import tempfile
from dataclasses import dataclass
from math import comb
from pathlib import Path

from .digital_vm import DigitalOrganism, TASK_A, TASK_B, execute_genome
from .resource_competition import CompetitionWorld, FOUNDER_GENOMES, classify

SCHEMA = "cano-low-loss-vacancy-v1"
POLICIES = ("closed", "continuous", "paced", "eligible")
COSTS = (0, 1, 2)
PRIMARY_COST = 1
PERIOD = 4


class VacancyWorld(CompetitionWorld):
    """Resource rotation fixed; remove at most one neutral survivor per eligible slot.

    "continuous" exactly reproduces legacy rotation_turnover,
    "closed" exactly reproduces legacy rotation_closed. "paced" only
    considers one vacancy every fourth tick. "eligible" additionally
    requires at least one energized viable parent; the removed survivor
    is selected neutrally, NOT by genotype or readiness. Removal costs one
    actual death and can happen with no later child; counted explicitly.
    """

    def __init__(self, *, policy: str, vacancy_period: int = PERIOD, **kwargs):
        if policy not in POLICIES:
            raise ValueError("Unknown vacancy policy")
        if type(vacancy_period) is not int or not 2 <= vacancy_period <= 12:
            raise ValueError("vacancy_period must be an int 2..12")
        super().__init__(allocation="rotation", turnover=False, **kwargs)
        self.policy = policy
        self.vacancy_period = vacancy_period
        self.forced_vacancies = 0
        self.mutation_events = 0  # Must remain zero for engineered founder experiment.

    def _mutate(self, genome):
        child = super()._mutate(genome)
        if child != tuple(genome):
            self.mutation_events += 1
        return child

    def step(self):
        self.tick += 1
        order = sorted(self.organisms, key=lambda o: o.identifier)
        if order:
            offset = (self.tick - 1) % len(order)
            order = order[offset:] + order[:offset]
        available = self.resources_per_tick
        survivors = []
        for organism in order:
            energy = organism.energy - 1
            matched = self.environment in organism.genome
            if matched and self.task_reward:
                energy += self.task_reward - self.task_cost
                self.reward_events += 1
                self.task_cost_spent += self.task_cost
            gain = min(2, available)
            available -= gain
            energy += gain
            if energy > 0:
                survivors.append(DigitalOrganism(organism.identifier, organism.parent,
                                                 organism.generation, energy, organism.genome))
            else:
                self.deaths += 1
        full = len(survivors) == self.capacity
        scheduled = self.tick % self.vacancy_period == 0
        eligible_parent = any(o.energy >= 8 and execute_genome(o.genome) is not None
                              for o in survivors)
        vacancy = (full and (
            self.policy == "continuous" or
            (self.policy == "paced" and scheduled) or
            (self.policy == "eligible" and scheduled and eligible_parent)
        ))
        if vacancy:
            victim = self.random.randrange(len(survivors))
            survivors.pop(victim)
            self.deaths += 1
            self.forced_vacancies += 1
        parents, children = [], []
        for organism in survivors:
            child_genome = execute_genome(organism.genome) if self.allow_replication else None
            if (child_genome is not None and organism.energy >= 8
                and len(survivors) + len(children) < self.capacity):
                children.append(DigitalOrganism(self.next_id, organism.identifier,
                                               organism.generation + 1, 3,
                                               self._mutate(child_genome)))
                self.next_id += 1
                self.births += 1
                organism = DigitalOrganism(organism.identifier, organism.parent,
                                          organism.generation, organism.energy - 4,
                                          organism.genome)
            parents.append(organism)
        self.organisms = parents + children
        if len(self.organisms) > self.capacity:
            raise AssertionError("population cap violated")
        return self.metrics()


def trace_vacancy(seed, policy, *, cost, reward, steps, period,
                  vacancy_period=PERIOD, allow_replication=True):
    if type(seed) is not int or seed < 0:
        raise ValueError("invalid seed")
    if policy not in POLICIES:
        raise ValueError("unknown policy")
    if type(cost) is not int or cost not in COSTS:
        raise ValueError("invalid cost")
    if type(reward) is not int or reward not in (0, 2):
        raise ValueError("invalid reward")
    if type(steps) is not int or not 20 <= steps <= 120:
        raise ValueError("invalid steps")
    if type(period) is not int or not 3 <= period <= 20:
        raise ValueError("invalid environment period")
    if type(allow_replication) is not bool:
        raise ValueError("invalid allow_replication")
    w = VacancyWorld(seed=seed, policy=policy, vacancy_period=vacancy_period,
                     task_reward=reward, task_cost=cost,
                     allow_replication=allow_replication)
    person_ticks = ab_person_ticks = capacity_ticks = 0
    first_birth = None
    population_trace = [len(w.organisms)]
    for tick in range(1, steps + 1):
        w.set_environment(TASK_A if ((tick-1)//period) % 2 == 0 else TASK_B)
        w.step()
        if first_birth is None and w.births > 0:
            first_birth = tick
        population = len(w.organisms)
        person_ticks += population
        capacity_ticks += int(population == w.capacity)
        ab_person_ticks += sum(classify(o.genome) == "AB" for o in w.organisms)
        population_trace.append(population)
    census = {key: sum(classify(o.genome) == key for o in w.organisms)
              for key in FOUNDER_GENOMES}
    if sum(census.values()) != len(w.organisms):
        raise AssertionError("unexpected genotype introduced")
    return {
        "population": len(w.organisms), "population_trace": population_trace,
        "genotype_counts": census, "ab_final_share": (census["AB"] / len(w.organisms)
                                                     if w.organisms else 0.),
        "person_ticks": person_ticks, "ab_person_ticks": ab_person_ticks,
        "first_birth": first_birth, "births": w.births, "deaths": w.deaths,
        "natural_deaths": w.deaths - w.forced_vacancies,
        "forced_vacancies": w.forced_vacancies,
        "reward_events": w.reward_events, "task_cost_spent": w.task_cost_spent,
        "capacity_ticks": capacity_ticks, "mutation_events": w.mutation_events,
        "max_generation": w.metrics()["max_generation"],
    }


def _ci(xs):
    avg = statistics.mean(xs)
    spread = 1.96 * statistics.stdev(xs) / (len(xs) ** .5) if len(xs) > 1 else 0
    return {"mean": avg, "ci95_low": avg-spread, "ci95_high": avg+spread,
            "n": len(xs), "method": "descriptive_paired_seeds_normal_approx"}


def _p(xs):
    positive = sum(x > 0 for x in xs)
    negative = sum(x < 0 for x in xs)
    n = positive + negative
    return sum(comb(n, k) for k in range(positive, n+1)) / 2**n if n else 1.0


def _check_design(seeds, steps, period, vacancy_period):
    if not isinstance(seeds, (list, tuple)) or not 20 <= len(seeds) <= 60:
        raise ValueError("must supply 20-60 unique paired seeds")
    if len(set(seeds)) != len(seeds) or any(type(x) is not int or x < 0 for x in seeds):
        raise ValueError("invalid paired seeds")
    if type(steps) is not int or not 20 <= steps <= 120:
        raise ValueError("invalid duration")
    if type(period) is not int or not 3 <= period <= 20:
        raise ValueError("invalid environment period")
    if type(vacancy_period) is not int or vacancy_period != PERIOD:
        raise ValueError("vacancy period must remain preregistered at 4")


def run_study(*, seeds=tuple(range(800, 830)), steps=80, period=12,
              vacancy_period=PERIOD):
    """Predefined cost-1 gate; cost-0/2 are sensitivity and negative controls.

    Main outcome: incremental reward-caused AB share for eligible-vacancy vs
    closed rotation. Secondary: eligible forced losses relative to continuous;
    preserve >=50% of continuous selection lift without >50% of its forced loss.
    """
    _check_design(seeds,steps,period,vacancy_period)
    trials = []
    for seed in seeds:
        for policy in POLICIES:
            for cost in COSTS:
                active=trace_vacancy(seed,policy,cost=cost,reward=2,steps=steps,
                                     period=period,vacancy_period=vacancy_period)
                null=trace_vacancy(seed,policy,cost=cost,reward=0,steps=steps,
                                   period=period,vacancy_period=vacancy_period)
                trials.append({"seed": seed, "policy": policy, "cost": cost,
                               "active": active, "null": null,
                               "causal_ab_share": active["ab_final_share"]-null["ab_final_share"],
                               "causal_ab_person_ticks": active["ab_person_ticks"]-null["ab_person_ticks"]})
    idx = {(x["seed"],x["policy"],x["cost"]):x for x in trials}
    by_cost=[]
    for cost in COSTS:
        diffs=[]; always_effect=[]; deaths=[]; always_deaths=[]; paced_effect=[]
        for seed in seeds:
            eligible=idx[seed,"eligible",cost]
            closed=idx[seed,"closed",cost]
            continuous=idx[seed,"continuous",cost]
            paced=idx[seed,"paced",cost]
            diffs.append(eligible["causal_ab_share"]-closed["causal_ab_share"])
            always_effect.append(continuous["causal_ab_share"]-closed["causal_ab_share"])
            paced_effect.append(paced["causal_ab_share"]-closed["causal_ab_share"])
            deaths.append(eligible["active"]["forced_vacancies"])
            always_deaths.append(continuous["active"]["forced_vacancies"])
        pos=sum(d>0 for d in diffs);neg=sum(d<0 for d in diffs)
        # Retrospective ceiling diagnostic: never used to relax primary gate.
        closed_ceiling = sum(idx[seed,"closed",cost]["active"]["ab_final_share"]==1.0
                             for seed in seeds)
        eligible_ceiling = sum(idx[seed,"eligible",cost]["active"]["ab_final_share"]==1.0
                               for seed in seeds)
        both_ceiling = sum(idx[seed,"closed",cost]["active"]["ab_final_share"]==1.0
                           and idx[seed,"eligible",cost]["active"]["ab_final_share"]==1.0
                           for seed in seeds)
        by_cost.append({"cost":cost,"positive_seeds":pos,"negative_seeds":neg,
                        "tied_seeds":len(seeds)-pos-neg,"exact_sign_p":_p(diffs),
                        "closed_active_ab_share_ceiling_seeds":closed_ceiling,
                        "eligible_active_ab_share_ceiling_seeds":eligible_ceiling,
                        "both_ceiling_seeds":both_ceiling,
                        "causal_ab_gain_over_closed":_ci(diffs),
                        "continuous_gain_over_closed":_ci(always_effect),
                        "paced_gain_over_closed":_ci(paced_effect),
                        "eligible_forced_deaths":_ci(deaths),
                        "continuous_forced_deaths":_ci(always_deaths)})
    conservation=all(x[variant]["population"]==12+x[variant]["births"]-x[variant]["deaths"]
                     and x[variant]["population"]<=12 and x[variant]["mutation_events"]==0
                     and x[variant]["deaths"]>=x[variant]["forced_vacancies"]
                     for x in trials for variant in ("active","null"))
    no_net=all(x["active"]["population_trace"]==x["null"]["population_trace"]
               and x["active"]["genotype_counts"]==x["null"]["genotype_counts"]
               and x["active"]["forced_vacancies"]==x["null"]["forced_vacancies"]
               for x in trials if x["cost"]==2)
    no_division=all(trace_vacancy(seed,"eligible",cost=1,reward=2,steps=steps,
                                  period=period,allow_replication=False)["births"]==0
                    for seed in seeds)
    nonnegative=all(x["active"]["forced_vacancies"]>=0 for x in trials)
    controls={"capacity_birth_death_accounting":conservation,
              "zero_net_reward_matches_null":no_net,
              "division_disabled_no_births":no_division,
              "forced_death_accounting":nonnegative}
    primary=by_cost[PRIMARY_COST]
    e=primary["eligible_forced_deaths"]["mean"]
    a=primary["continuous_forced_deaths"]["mean"]
    positive=primary["causal_ab_gain_over_closed"]["mean"]
    all_gain=primary["continuous_gain_over_closed"]["mean"]
    # The gate was fixed before examining the 800/900 seed partitions.
    # The retention criterion also prevents a tautological 'no deaths' win.
    gate=(primary["positive_seeds"]>=len(seeds)/2 and primary["exact_sign_p"]<.05
          and primary["causal_ab_gain_over_closed"]["ci95_low"]>0
          and a>0 and e<=.5*a and all_gain>0 and positive>=.5*all_gain
          and all(controls.values()))
    return {"schema":SCHEMA,
            "design": {"seeds":list(seeds),"steps":steps,"environment_period":period,
                       "vacancy_period":vacancy_period,"capacity":12,"resource_per_tick":1,
                       "mutation_rate":0,"initial_genotype_counts":{"A":4,"B":4,"AB":4},
                       "policies":list(POLICIES),"costs":list(COSTS),"primary_cost":PRIMARY_COST,
                       "reward":2,"primary_metric":"paired (eligible reward-null AB share) minus (closed reward-null AB share), task cost 1",
                       "gate":"in EACH separate seed cohort >=50% all seeds positive, one-sided exact sign p<.05, normal-approx paired 95% lower>0; eligible <=50% continuous forced deaths and retains >=50% continuous AB share selection gain; negative controls pass",
                       "other_costs":"cost 0 explorational; cost 2 zero-net negative control"},
            "per_cost":by_cost,"negative_controls":controls,
            "strict_low_loss_selection_demonstrated":gate,"trials":trials,
            "limitations":["Engineered A/B/AB genomes at inception; no novel genotype evolution or learning.",
                           "Neutral vacancy deliberately kills real digital individuals; not a zero-death repair.",
                           "Seeded toy simulation with fixed 12 capacity and nonuniform energy rewards, not real-world evidence.",
                           "Normal confidence intervals cover only synthetic seeds; multiple cost alternatives are not confirmatory.",
                           "No changes to existing GenomeWorld, production CANO, calendar, Render or PostgreSQL."]}


def _encode(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",", ":"))+"\n").encode("utf-8")


def save_report(report,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    obj={"report":report,"sha256":hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        if verify_report(path)!=obj:
            raise FileExistsError("conflicting existing report")
        return obj
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix=".cano-low-loss-")
    try:
        with os.fdopen(fd,"wb") as h:
            h.write(_encode(obj));h.flush();os.fsync(h.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    verify_report(path)
    return obj


def verify_report(path):
    obj=json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(obj,dict) or set(obj)!={"report","sha256"}:
        raise ValueError("bad report schema")
    if hashlib.sha256(_encode(obj["report"])).hexdigest()!=obj["sha256"]:
        raise ValueError("report digest mismatch")
    d=obj["report"]["design"]
    expected=run_study(seeds=d["seeds"],steps=d["steps"],
                       period=d["environment_period"],vacancy_period=d["vacancy_period"])
    if expected!=obj["report"]:
        raise ValueError("independent replay mismatch")
    return obj


def main(argv=None):
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-start",type=int,default=800)
    parser.add_argument("--seeds",type=int,default=30)
    parser.add_argument("--output",required=True,type=Path)
    args=parser.parse_args(argv)
    doc=save_report(run_study(seeds=tuple(range(args.seed_start,args.seed_start+args.seeds))),args.output)
    report=doc["report"]
    cost=report["per_cost"][PRIMARY_COST]
    print(json.dumps({"digest":doc["sha256"],"positive_seeds":cost["positive_seeds"],
                      "forced_deaths_eligible":cost["eligible_forced_deaths"]["mean"],
                      "forced_deaths_continuous":cost["continuous_forced_deaths"]["mean"],
                      "gate":report["strict_low_loss_selection_demonstrated"]},sort_keys=True))

if __name__=="__main__":main()
