"""Strict bounded tests of genotype-neutral, lower-loss vacancy experiments."""
import copy
import json
import hashlib
import tempfile
import unittest
from pathlib import Path
from organism_lab.resource_competition import trace_world
from organism_lab.low_loss_turnover import (VacancyWorld, trace_vacancy, run_study, save_report, verify_report, _encode)

class LowLossTurnoverTests(unittest.TestCase):
    def test_closed_continuous_match_existing_legacy_engine(self):
        for seed in (800, 811):
            for policy, arm in [('closed','rotation_closed'), ('continuous','rotation_turnover')]:
                old=trace_world(seed,arm,cost=1,reward=2,steps=40,period=12)
                new=trace_vacancy(seed,policy,cost=1,reward=2,steps=40,period=12)
                for key in ('population_trace','genotype_counts','births','deaths','ab_final_share','ab_person_ticks','first_birth'):
                    self.assertEqual(old[key],new[key],(seed,policy,key))

    def test_paced_vacancies_are_bounded_and_neutral(self):
        for policy in ('paced','eligible'):
            result=trace_vacancy(812,policy,cost=0,reward=2,steps=80,period=12)
            self.assertLessEqual(result['forced_vacancies'],20)
            self.assertEqual(result['population'],12+result['births']-result['deaths'])
            self.assertLessEqual(result['population'],12)
            self.assertEqual(sum(result['genotype_counts'].values()),result['population'])
            self.assertEqual(len(result['population_trace']),81)
            self.assertEqual(result['mutation_events'],0)

    def test_energy_neutral_cost_two_matches_zero_reward(self):
        for policy in ('closed','continuous','paced','eligible'):
            positive=trace_vacancy(808,policy,cost=2,reward=2,steps=45,period=12)
            null=trace_vacancy(808,policy,cost=2,reward=0,steps=45,period=12)
            for key in ('population_trace','genotype_counts','births','deaths','forced_vacancies','ab_person_ticks'):
                self.assertEqual(positive[key],null[key],(policy,key))

    def test_no_division_stops_births_even_if_vacancies_created(self):
        result=trace_vacancy(810,'eligible',cost=1,reward=2,steps=60,period=12,allow_replication=False)
        self.assertEqual(result['births'],0)

    def test_bad_inputs_fail_closed(self):
        for kw in ({'policy':'oops'},{'cost':-1},{'reward':1},{'steps':999}, {'period':2}, {'vacancy_period':0}):
            args=dict(seed=800,policy='eligible',cost=1,reward=2,steps=40,period=12)
            args.update(kw)
            with self.subTest(kw=kw), self.assertRaises(ValueError):trace_vacancy(**args)
        with self.assertRaises(ValueError):run_study(seeds=(800,)*20)

    @classmethod
    def setUpClass(cls):
        cls.report=run_study(seeds=tuple(range(800,820)),steps=40,period=12)

    def test_study_is_paired_bounded_reproducible_and_transparent(self):
        r=self.report
        self.assertEqual(r,run_study(seeds=tuple(range(800,820)),steps=40,period=12))
        self.assertEqual(len(r['trials']),20*4*3)
        self.assertEqual(r['design']['primary_cost'],1)
        self.assertEqual(r['design']['vacancy_period'],4)
        self.assertTrue(all(r['negative_controls'].values()))
        self.assertIn('strict_low_loss_selection_demonstrated',r)
        self.assertIn('forced_vacancies',r['trials'][0]['active'])

    def test_primary_ceiling_is_explicitly_counted_without_changing_gate(self):
        r=self.report
        primary=r['per_cost'][1]
        actual=sum(x['active']['ab_final_share']==1.0
                   for x in r['trials'] if x['cost']==1 and x['policy']=='closed')
        eligible=sum(x['active']['ab_final_share']==1.0
                     for x in r['trials'] if x['cost']==1 and x['policy']=='eligible')
        self.assertEqual(primary['closed_active_ab_share_ceiling_seeds'],actual)
        self.assertEqual(primary['eligible_active_ab_share_ceiling_seeds'],eligible)
        self.assertEqual(primary['both_ceiling_seeds'],sum(
            1 for seed in r['design']['seeds']
            if next(x for x in r['trials'] if x['seed']==seed and x['cost']==1 and x['policy']=='closed')['active']['ab_final_share']==1.0
            and next(x for x in r['trials'] if x['seed']==seed and x['cost']==1 and x['policy']=='eligible')['active']['ab_final_share']==1.0))

    def test_paced_cannot_force_more_deaths_than_continuous(self):
        for seed in range(800,815):
            a=trace_vacancy(seed,'continuous',cost=1,reward=2,steps=40,period=12)
            b=trace_vacancy(seed,'eligible',cost=1,reward=2,steps=40,period=12)
            self.assertLessEqual(b['forced_vacancies'],a['forced_vacancies'])

    def test_digest_replay_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'study.json'
            original=save_report(self.report,p)
            self.assertEqual(original,verify_report(p))
            before=p.read_bytes()
            self.assertEqual(save_report(self.report,p),original)
            self.assertEqual(before,p.read_bytes())
            x=json.loads(before)
            x['report']['trials'][0]['active']['deaths']=999
            p.write_text(json.dumps(x),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'digest'):
                verify_report(p)
            x['sha256']=hashlib.sha256(_encode(x['report'])).hexdigest()
            p.write_text(json.dumps(x),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'replay'):
                verify_report(p)

if __name__=='__main__':unittest.main()
