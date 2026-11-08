"""Behavioral verification of a finite selection mechanism, not agent learning."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from organism_lab.digital_vm import GenomeWorld, DigitalOrganism, TASK_A, TASK_B
from organism_lab.resource_competition import (
    ARMS, COSTS, CompetitionWorld, FOUNDER_GENOMES, _encode,
    run_competition, save_report, trace_world, verify_report,
)


class ResourceCompetitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=run_competition(seeds=tuple(range(600,620)),steps=40)

    def test_result_records_paired_fitness_and_negative_control(self):
        r=self.report
        self.assertEqual(r['design']['seeds'],list(range(600,620)))
        self.assertTrue(all(r['negative_controls'].values()))
        self.assertEqual(r['design']['initial_allele_counts'], {'A':4,'B':4,'AB':4})
        self.assertEqual(len(r['trials']),20*4*3)
        self.assertEqual([v['task_cost'] for v in r['per_cost']],list(COSTS))
        self.assertIn('turnover', r['design']['arms'][-1])

    def test_baseline_seniority_closed_exactly_matches_original_vm_one_step(self):
        w=CompetitionWorld(seed=610,allocation='seniority',turnover=False,
                           task_cost=0,task_reward=2)
        original=deepcopy(w)
        for phase in [TASK_A,TASK_A,TASK_B,TASK_A,TASK_B]:
            w.set_environment(phase);original.set_environment(phase)
            actual=w.step()
            expected=GenomeWorld.step(original)
            self.assertEqual(actual,expected)
            self.assertEqual(w.organisms,original.organisms)

    def test_resource_round_robin_rotates_rather_than_privileging_oldest(self):
        w=CompetitionWorld(seed=601,allocation='rotation',turnover=False,
                           task_cost=0,task_reward=0,allow_replication=False)
        w.step()
        self.assertEqual(next(o.energy for o in w.organisms if o.identifier==0),4)
        w.step()
        self.assertEqual(next(o.energy for o in w.organisms if o.identifier==0),3)
        self.assertEqual(next(o.energy for o in w.organisms if o.identifier==1),3)
        self.assertEqual(next(o.energy for o in w.organisms if o.identifier==2),2)

    def test_neutral_turnover_creates_real_vacancy_at_full_cap(self):
        base=CompetitionWorld(seed=602,allocation='seniority',turnover=False,
                              task_reward=2,task_cost=0)
        treatment=CompetitionWorld(seed=602,allocation='seniority',turnover=True,
                              task_reward=2,task_cost=0)
        base.step();treatment.step()
        self.assertEqual(base.deaths,0)
        self.assertEqual(treatment.deaths,1)
        self.assertEqual(len(treatment.organisms),11)
        self.assertEqual(len(base.organisms),12)

    def test_zero_net_reward_null_matches_exact_genotypes_and_trajectories(self):
        for arm in ARMS:
            with self.subTest(arm=arm):
                active=trace_world(607,arm,cost=2,reward=2,steps=50,period=10)
                null=trace_world(607,arm,cost=2,reward=0,steps=50,period=10)
                for field in ['population_trace','genotype_counts','births','deaths',
                              'person_ticks','ab_person_ticks','first_birth']:
                    self.assertEqual(active[field],null[field])
                self.assertGreater(active['reward_events'],0)
                self.assertEqual(null['reward_events'],0)

    def test_AB_lineage_can_survive_alternating_task_when_null_goes_extinct(self):
        a=CompetitionWorld(seed=610,allocation='seniority',turnover=False,
                           task_reward=2,task_cost=0,allow_replication=False)
        b=CompetitionWorld(seed=610,allocation='seniority',turnover=False,
                           task_reward=0,task_cost=0,allow_replication=False)
        for w in [a,b]:
            # Isolate the task effect from the VM's free per-tick resource.
            w.resources_per_tick=0
            w.organisms=[DigitalOrganism(0,None,0,3,FOUNDER_GENOMES['AB'])]
        for tick in range(1,16):
            env=TASK_A if (tick//4)%2==0 else TASK_B
            a.set_environment(env);b.set_environment(env)
            a.step();b.step()
        self.assertEqual(len(a.organisms),1)
        self.assertEqual(len(b.organisms),0)

    def test_bounded_lineages_and_accounting_even_under_neutral_turnover(self):
        r=self.report
        for t in r['trials']:
            for case in ('active','null'):
                data=t[case]
                self.assertEqual(data['population'],12+data['births']-data['deaths'])
                self.assertLessEqual(data['population'],12)
                self.assertEqual(len(data['population_trace']),41)
                self.assertEqual(sum(data['genotype_counts'].values()),data['population'])
                self.assertGreaterEqual(data['person_ticks'],0)
                self.assertEqual(data['initial_counts'], {'A':4,'B':4,'AB':4})

    def test_deterministic_and_no_division_controls(self):
        r=run_competition(seeds=tuple(range(600,620)),steps=40)
        self.assertEqual(r,self.report)
        self.assertTrue(r['negative_controls']['division_disabled_zero_births'])
        for seed in range(600,620):
            x=trace_world(seed,'rotation_turnover',cost=0,reward=2,steps=40,
                          period=12,allow_replication=False)
            self.assertEqual(x['births'],0)

    def test_parameter_validation_fails_closed(self):
        for kw in [dict(seeds=(1,)*20),dict(seeds=tuple(range(19))),
                   dict(steps=1000),dict(period=0),dict(steps=True)]:
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                run_competition(**kw)
        for kw in [dict(allocation='random'),dict(turnover=1),
                   dict(task_cost=9),dict(capacity=13),dict(resources=50)]:
            with self.subTest(kw=kw),self.assertRaises(ValueError):
                CompetitionWorld(seed=1,**kw)

    def test_atomic_save_replay_idempotence_and_conflicting_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'data'/'result.json'
            self.assertEqual(save_report(self.report,p),verify_report(p))
            original=p.read_bytes()
            self.assertEqual(save_report(self.report,p),verify_report(p))
            self.assertEqual(p.read_bytes(),original)
            changed=deepcopy(self.report)
            changed['design']['period']=7
            with self.assertRaises(FileExistsError):save_report(changed,p)
            self.assertEqual(p.read_bytes(),original)

    def test_tampering_and_forged_checksum_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'result.json'
            save_report(self.report,p)
            doc=json.loads(p.read_text())
            tampered=deepcopy(doc)
            tampered['report']['trials'][0]['active']['births']=10000
            p.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError,'Digest'):
                verify_report(p)
            tampered['sha256']=hashlib.sha256(_encode(tampered['report'])).hexdigest()
            p.write_text(json.dumps(tampered))
            with self.assertRaisesRegex(ValueError,'replay'):
                verify_report(p)

if __name__=='__main__':unittest.main()
