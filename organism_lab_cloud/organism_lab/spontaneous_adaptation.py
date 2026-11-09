"""Finite digital genotype-origin experiment; no real agent self-improvement.

Research-only subclass: original VM, existing CompetitionWorld and VacancyWorld
are unmodified. No A+B founder; only stochastic grammar-constrained point mutation
can create that four-locus composite. Not a new, previously unseen task.
"""
from __future__ import annotations

from random import Random
from .digital_vm import COPY_REST, DIVIDE, NOP, TASK_A, TASK_B, DigitalOrganism, GenomeWorld
from .resource_competition import FOUNDER_GENOMES
from .low_loss_turnover import VacancyWorld

TASK_ALLELES = (NOP, TASK_A, TASK_B)

class DiscoveryWorld(VacancyWorld):
    """Start 6 A-only and 6 B-only; allow safe mutation of two task loci."""
    def __init__(self, *, seed, policy, mutation_rate, allow_replication=True, reward=2):
        if type(seed) is not int or seed < 0:
            raise ValueError('seed must be nonnegative integer')
        if type(mutation_rate) not in (int,float) or not 0 <= mutation_rate <= 1:
            raise ValueError('mutation_rate must be 0..1 (no booleans)')
        if policy not in ('closed','eligible'):
            raise ValueError('Only predeclared closed/eligible policy choices allowed')
        if type(allow_replication) is not bool or reward not in (0,2) or type(reward) is not int:
            raise ValueError('Invalid reward or division toggle')
        super().__init__(seed=seed,policy=policy,task_cost=1,task_reward=reward,
                         allow_replication=allow_replication)
        founder_keys=['A']*6+['B']*6
        Random(seed+104729).shuffle(founder_keys)
        self.organisms=[DigitalOrganism(i,None,0,4,FOUNDER_GENOMES[g])
                        for i,g in enumerate(founder_keys)]
        self.next_id=12
        self.mutation_rate=float(mutation_rate)
        self.ab_mutation_births=0

    def _mutate(self, genome):
        if len(genome)!=4 or genome[0]!=COPY_REST or genome[3]!=DIVIDE or any(
                op not in TASK_ALLELES for op in genome[1:3]):
            raise ValueError('Mutations require viable 4-locus task grammar')
        # Keep SAME complete RNG candidate generation as parent VM; no AB targeting.
        candidate=list(GenomeWorld._mutate(self,genome))
        candidate[0],candidate[3]=COPY_REST,DIVIDE
        for pos in (1,2):
            if candidate[pos] not in TASK_ALLELES:
                candidate[pos]=genome[pos]
        child=tuple(candidate)
        if child!=tuple(genome):
            self.mutation_events+=1
        if child==FOUNDER_GENOMES['AB'] and tuple(genome)!=FOUNDER_GENOMES['AB']:
            self.ab_mutation_births+=1
        return child

from collections import Counter
from copy import deepcopy
from math import comb
import hashlib
import json
from pathlib import Path
import statistics

from .compositional_transfer_study import holdout_composition

SCHEMA = 'cano-spontaneous-ab-lineage-v1'
ARMS = ('eligible_mutation','closed_mutation','eligible_no_mutation','eligible_no_division','eligible_no_reward')


def _ci(xs):
    avg=statistics.mean(xs)
    half=1.96*statistics.stdev(xs)/(len(xs)**.5) if len(xs)>1 else 0.0
    return {'mean':avg,'ci95_low':avg-half,'ci95_high':avg+half,'n':len(xs),
            'method':'normal_approx_description_fixed_deterministic_seeds'}


def _sign(xs):
    npos=sum(x>0 for x in xs)
    nneg=sum(x<0 for x in xs)
    n=npos+nneg
    return sum(comb(n,k) for k in range(npos,n+1))/2**n if n else 1.0


def simulate(seed,arm,*,steps=120,period=12,mutation_rate=.08,holdout_steps=20):
    if arm not in ARMS:raise ValueError('arm not predeclared')
    if type(steps) is not int or not 20<=steps<=160:raise ValueError('invalid ticks')
    if type(period) is not int or not 3<=period<=20:raise ValueError('invalid period')
    if type(holdout_steps) is not int or not 1<=holdout_steps<=50:raise ValueError('invalid holdout')
    if type(mutation_rate) not in (int,float) or not 0<=mutation_rate<=1:raise ValueError('invalid mutation rate')
    policy='closed' if arm=='closed_mutation' else 'eligible'
    rate=0 if arm=='eligible_no_mutation' else mutation_rate
    rep=arm!='eligible_no_division'
    reward=0 if arm=='eligible_no_reward' else 2
    world=DiscoveryWorld(seed=seed,policy=policy,mutation_rate=rate,
                         allow_replication=rep,reward=reward)
    original=tuple(o.genome for o in world.organisms)
    if FOUNDER_GENOMES['AB'] in original:raise AssertionError('AB founder would invalidate experiment')
    first_ab_tick=None;first_ab_mutant_parent=None;person_ticks=0;ab_person_ticks=0
    peak_gen=0;population_trace=[len(world.organisms)]
    for tick in range(1,steps+1):
        before={o.identifier:o for o in world.organisms}
        old_id=world.next_id
        world.set_environment(TASK_A if ((tick-1)//period)%2==0 else TASK_B)
        world.step()
        newborn=[o for o in world.organisms if o.identifier>=old_id]
        if first_ab_tick is None:
            ab_new=[o for o in newborn if o.genome==FOUNDER_GENOMES['AB']]
            if ab_new:
                first_ab_tick=tick
                # Parent lookup from BEFORE step: never hallucinate ancestry.
                first_ab_mutant_parent=list(before[ab_new[0].parent].genome)
                if ab_new[0].parent not in before:raise AssertionError('Missing parent provenance')
        n=len(world.organisms)
        population_trace.append(n)
        person_ticks+=n
        ab_person_ticks+=sum(o.genome==FOUNDER_GENOMES['AB'] for o in world.organisms)
        peak_gen=max(peak_gen,world.metrics()['max_generation'])
        if n>world.capacity or n<0:raise AssertionError('capacity violation')
        if n!=12+world.births-world.deaths:raise AssertionError('population accounting failure')
    ab_final=sum(o.genome==FOUNDER_GENOMES['AB'] for o in world.organisms)
    # A+B is NOT rewarded in training; only the previously-unrewarded conjunction holdout.
    awarded=holdout_composition(world,steps=holdout_steps,reward=2)
    none=holdout_composition(world,steps=holdout_steps,reward=0)
    return {'seed':seed,'arm':arm,'genomes_initial':[list(x) for x in original],
            'first_new_ab_tick':first_ab_tick,'first_new_ab_parent_genome':first_ab_mutant_parent,
            'ab_mutation_births':world.ab_mutation_births,'mutation_events':world.mutation_events,
            'ab_person_ticks':ab_person_ticks,'person_ticks':person_ticks,
            'ab_final_count':ab_final,'final_population':len(world.organisms),
            'total_births':world.births,'deaths':world.deaths,
            'forced_vacancies':world.forced_vacancies,'max_generation':peak_gen,
            'population_trace':population_trace,
            'holdout_c_reward':awarded,'holdout_zero_reward':none,
            'holdout_c_population_bonus':awarded['population']-none['population'],
            'holdout_c_new_births_bonus':awarded['births_added']-none['births_added']}


def _validate_study(seeds,steps,period,mutation_rate,holdout_steps):
    if not isinstance(seeds,(list,tuple)) or not 20<=len(seeds)<=40 or any(type(x) is not int or x<0 for x in seeds) or len(seeds)!=len(set(seeds)):
        raise ValueError('20..40 unique nonnegative paired seeds required')
    if type(steps) is not int or not 20<=steps<=160:raise ValueError('bad steps')
    if type(period) is not int or not 3<=period<=20:raise ValueError('bad period')
    if type(mutation_rate) not in (int,float) or not 0<=mutation_rate<=1:raise ValueError('bad mutation rate')
    if type(holdout_steps) is not int or not 1<=holdout_steps<=50:raise ValueError('bad holdout')


def run_study(*,seeds=tuple(range(1200,1230)),steps=120,period=12,
              mutation_rate=.08,holdout_steps=20):
    """Predetermined five-arm study; first independent cohort then new seeds.

    Primary: eligible vs closed mutation difference in functional AB person-ticks,
    AND emergence in >=half seeds, plus causal novel-C holdout bonus not negative.
    This gate is purposely allowed to FAIL. No claims of general adaptation.
    """
    _validate_study(seeds,steps,period,mutation_rate,holdout_steps)
    trials=[simulate(seed,arm,steps=steps,period=period,mutation_rate=mutation_rate,
                     holdout_steps=holdout_steps) for seed in seeds for arm in ARMS]
    idx={(t['seed'],t['arm']):t for t in trials}
    emergence=[idx[s,'eligible_mutation']['ab_mutation_births']>0 for s in seeds]
    emergence_n=sum(emergence)
    active_diffs=[idx[s,'eligible_mutation']['ab_person_ticks']-idx[s,'closed_mutation']['ab_person_ticks'] for s in seeds]
    holdout_diffs=[idx[s,'eligible_mutation']['holdout_c_population_bonus']-idx[s,'closed_mutation']['holdout_c_population_bonus'] for s in seeds]
    negative={
      'no_mutation_never_creates_ab':all(idx[s,'eligible_no_mutation']['ab_mutation_births']==0 and idx[s,'eligible_no_mutation']['ab_final_count']==0 for s in seeds),
      'no_division_zero_births':all(idx[s,'eligible_no_division']['total_births']==0 for s in seeds),
      'no_reward_control_recorded':all(idx[s,'eligible_no_reward']['holdout_zero_reward']['rewarded_steps']==0 for s in seeds),
      'founders_AB_absent':all(all(tuple(g)!=FOUNDER_GENOMES['AB'] for g in x['genomes_initial']) for x in trials),
      'population_birth_death_conserved':all(x['final_population']==12+x['total_births']-x['deaths'] for x in trials),
      'mutation_parent_provenance':all((x['first_new_ab_parent_genome'] is not None and len(x['first_new_ab_parent_genome'])==4 and tuple(x['first_new_ab_parent_genome'])!=FOUNDER_GENOMES['AB']) for x in trials if x['first_new_ab_tick'] is not None),
    }
    positive=sum(d>0 for d in active_diffs)
    active_ci=_ci(active_diffs)
    holdout_ci=_ci(holdout_diffs)
    gate=(emergence_n>=len(seeds)*.5 and positive>=len(seeds)*.5
          and _sign(active_diffs)<.05 and active_ci['ci95_low']>0
          and holdout_ci['ci95_low']>=0 and all(negative.values()))
    return {'schema':SCHEMA,'design':{'seeds':list(seeds),'steps':steps,
             'period':period,'holdout_steps':holdout_steps,'mutation_rate':mutation_rate,
             'initial_genotypes':'6 A-only + 6 B-only, shuffled by seed; AB=0',
             'policies':list(ARMS),'resource_per_tick':1,'capacity':12,
             'task_reward':2,'task_energy_cost':1,'vacancy_period':4,
             'training':'A then B alternating every 12 ticks; NEVER reward A AND B in training',
             'holdout':'20 ticks normalized energy3, mutation frozen, previously-unrewarded AB conjunction C reward2 vs reward0',
             'primary_metric':'paired eligible-mutating minus closed-mutating AB-bearing organism-person-ticks, extinct=0',
             'acceptance':'within each independent 30-seed group: AB first emergence in >=50% seeds; >=50% paired positive time advantage, exact one-sided sign p<0.05, mean paired ~95% lower>0; holdout causal terminal bonus difference ~95% lower>=0, all controls. All required; otherwise FAIL'},
            'positive_seeds':positive,'negative_seeds':sum(x<0 for x in active_diffs),
            'tied_seeds':sum(x==0 for x in active_diffs),'emergence_seeds':emergence_n,
            'exact_one_sided_sign_p':_sign(active_diffs),'paired_ab_time_advantage':active_ci,
            'paired_c_holdout_advantage':holdout_ci,'negative_controls':negative,
            'adaptation_demonstrated':gate,
            'holdout_positive_seeds':sum(idx[s,'eligible_mutation']['holdout_c_population_bonus']>0 for s in seeds),
            'ab_mutation_births_total':sum(idx[s,'eligible_mutation']['ab_mutation_births'] for s in seeds),
            'ab_final_count_total':sum(idx[s,'eligible_mutation']['ab_final_count'] for s in seeds),
            'eligible_forced_vacancies_total':sum(idx[s,'eligible_mutation']['forced_vacancies'] for s in seeds),
            'closed_forced_vacancies_total':sum(idx[s,'closed_mutation']['forced_vacancies'] for s in seeds),
            'trials':trials,
            'limitations':['Finite digital VM; not living cells, self-directed agents or LLM self-training.',
             'A and B tasks known; AB conjunction novel only to reward schedule, not new instruction or externally drawn benchmark.',
             'Grammar constrained by engineer; mutation rates differ by accepted allele; no task-targeting during mutation.',
             'Changes from seed to seed are deterministic under the seeded model, not real-world replication.',
             'No preregistration outside this repo; thresholds fixed within code before inspected results.']}


def _encode(value):
    return (json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()


def save_report(report,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    doc={'report':report,'sha256':hashlib.sha256(_encode(report)).hexdigest()}
    if path.exists():
        with path.open(encoding='utf-8') as f:old=json.load(f)
        if old!=doc:raise FileExistsError('Different report already saved')
    else:
        import os,tempfile
        fd,tmp=tempfile.mkstemp(prefix='.ab-novel-',dir=str(path.parent))
        try:
            with os.fdopen(fd,'wb') as w:
                w.write(_encode(doc));w.flush();os.fsync(w.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return verify_report(path)


def verify_report(path):
    doc=json.loads(Path(path).read_text(encoding='utf-8'))
    if set(doc)!={'report','sha256'}:raise ValueError('bad document format')
    if hashlib.sha256(_encode(doc['report'])).hexdigest()!=doc['sha256']:
        raise ValueError('digest mismatch')
    d=doc['report']['design']
    rebuilt=run_study(seeds=d['seeds'],steps=d['steps'],period=d['period'],
                      mutation_rate=d['mutation_rate'],holdout_steps=d['holdout_steps'])
    if rebuilt!=doc['report']:raise ValueError('independent recomputation mismatch')
    return doc
