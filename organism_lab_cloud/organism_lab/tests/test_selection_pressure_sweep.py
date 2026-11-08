"""Behavioral tests for finite prospective capacity/resource experiment."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from organism_lab.compositional_transfer_study import (
    FOUNDER, TaskGrammarWorld, holdout_composition,
)
from organism_lab.digital_vm import COPY_REST, DIVIDE, NOP, TASK_A, TASK_B, DigitalOrganism
from organism_lab.selection_pressure_sweep import (
    PRIMARY_CAPACITY, PRIMARY_RESOURCE, matched_snapshot, run_pressure_sweep,
    trace_composition, save_report, verify_report,
)


class SelectionPressureTests(unittest.TestCase):
    def example(self, n=5, c_fraction=2):
        w = TaskGrammarWorld(seed=17, capacity=48, resources_per_tick=1,
                             mutation_rate=0, initial_genome=FOUNDER, mode='task_grammar')
        w.organisms = [DigitalOrganism(i, None, 0, 50,
                        (COPY_REST, TASK_A, TASK_B, DIVIDE) if i < c_fraction
                        else (COPY_REST, TASK_A, NOP, DIVIDE)) for i in range(n)]
        w.next_id = n
        return w

    def test_holdout_timecourse_matches_prior_reference(self):
        w = self.example(n=5, c_fraction=3)
        copy = deepcopy(w)
        for reward in (0, 2):
            expected = holdout_composition(w, steps=12, reward=reward)
            found = trace_composition(w, steps=12, reward=reward, capacity=48, resources=1)
            self.assertEqual(found['population'], expected['population'])
            self.assertEqual(found['births_added'], expected['births_added'])
            self.assertEqual(found['reward_events'], expected['rewarded_steps'])
            self.assertEqual(found['novel_carriers'], expected['novel_carriers'])
            self.assertEqual(len(found['population_trace']), 13)
            self.assertEqual(sum(found['population_trace'][1:]), found['person_ticks'])
        self.assertEqual(w.organisms, copy.organisms)
        self.assertEqual(w.metrics(), copy.metrics())

    def test_first_division_and_reward_null(self):
        w = self.example(n=2, c_fraction=2)
        reward = trace_composition(w, steps=12, reward=2, capacity=24, resources=0)
        null = trace_composition(w, steps=12, reward=0, capacity=24, resources=0)
        self.assertIsNotNone(reward['first_division_tick'])
        self.assertIsNone(null['first_division_tick'])
        self.assertGreater(reward['births_added'], null['births_added'])
        self.assertGreater(reward['person_ticks'], null['person_ticks'])
        self.assertEqual(null['reward_events'], 0)

    def test_matched_samples_equalized_and_source_unchanged(self):
        a = self.example(n=18, c_fraction=5)
        b = self.example(n=7, c_fraction=2)
        original_a, original_b = deepcopy(a), deepcopy(b)
        x,y,amount = matched_snapshot(a, b, max_individuals=12)
        self.assertEqual(amount, 7)
        self.assertEqual(len(x.organisms), len(y.organisms))
        self.assertEqual([o.energy for o in x.organisms], [3]*7)
        self.assertTrue(all(o.energy==3 for o in y.organisms))
        self.assertEqual(x.organisms, matched_snapshot(a,b,max_individuals=12)[0].organisms)
        self.assertEqual(a.organisms,original_a.organisms)
        self.assertEqual(b.organisms,original_b.organisms)

    def test_capacity_zero_resource_bounds_and_immutable_input(self):
        w = self.example(n=12,c_fraction=2)
        original = deepcopy(w)
        for cap in (12,24,48):
            for res in (0,1,4):
                t=trace_composition(w,steps=20,reward=2,capacity=cap,resources=res)
                self.assertTrue(all(0 <= pop <= cap for pop in t['population_trace']))
                self.assertEqual(t['capacity_ticks'],sum(pop==cap for pop in t['population_trace'][1:]))
                if t['first_division_tick'] is not None:
                    self.assertTrue(1<=t['first_division_tick']<=20)
        self.assertEqual(w.organisms, original.organisms)
        with self.assertRaises(ValueError):
            trace_composition(w,steps=20,reward=2,capacity=5,resources=1)
        with self.assertRaises(ValueError):
            trace_composition(w,steps=20,reward=2,capacity=24,resources=-1)

    def test_paired_grid_conservation_and_negative_control(self):
        p = run_pressure_sweep(seeds=tuple(range(300,320)),steps=45,shift_tick=15,
                               holdout_steps=8, capacities=(12,24),resource_levels=(0,1),sample_size=8)
        self.assertEqual(p['schema'],'cano-selection-pressure-sweep-v1')
        self.assertEqual(len(p['trials']),20*4)
        self.assertEqual(len(p['grid']),4)
        self.assertEqual(p['design']['primary'],{'capacity':PRIMARY_CAPACITY,'resource':PRIMARY_RESOURCE})
        for row in p['trials']:
            self.assertEqual(row['grammar']['starting_population'], row['core']['starting_population'])
            self.assertEqual(row['grammar']['null']['reward_events'],0)
            self.assertEqual(row['core']['null']['reward_events'],0)
            self.assertLessEqual(row['grammar']['reward']['population'],row['capacity'])
            self.assertLessEqual(row['core']['reward']['population'],row['capacity'])
        self.assertTrue(p['controls']['null_reward_never_earns_task_bonus'])
        self.assertTrue(p['controls']['paired_initial_population_equal'])

    def test_reproducible_and_invalid_specs_rejected(self):
        kw=dict(seeds=tuple(range(500,520)),steps=35,shift_tick=12,holdout_steps=5,
                capacities=(12,24),resource_levels=(0,1),sample_size=5)
        a=run_pressure_sweep(**kw)
        self.assertEqual(a,run_pressure_sweep(**kw))
        for change in ({'seeds':tuple(range(19))}, {'seeds':(500,)*20},
                       {'steps':1001},{'capacities':(24,24)},{'resource_levels':(-1,1)},
                       {'sample_size':0},{'holdout_steps':80},{'mutation_rate':1.2}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                run_pressure_sweep(**{**kw,**change})

    def test_report_is_idempotent_and_tamper_detected_even_with_forged_digest(self):
        report=run_pressure_sweep(seeds=tuple(range(600,620)),steps=35,shift_tick=12,
                                  holdout_steps=5,capacities=(12,24),resource_levels=(0,1),
                                  sample_size=6)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'research'/'report.json'
            first=save_report(report,path)
            self.assertEqual(verify_report(path),first)
            self.assertEqual(save_report(report,path),first)
            data=path.read_bytes()
            modified=json.loads(data)
            modified['report']['trials'][0]['delta_person_ticks_causal']=999999
            path.write_text(json.dumps(modified),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'digest'):
                verify_report(path)
            from organism_lab.selection_pressure_sweep import _encode
            modified['sha256']=hashlib.sha256(_encode(modified['report'])).hexdigest()
            path.write_text(json.dumps(modified),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'recomput'):
                verify_report(path)
            path.write_bytes(data)
            self.assertEqual(verify_report(path),first)

    def test_equalized_population_does_not_imply_success(self):
        a=self.example(n=0,c_fraction=0)
        b=self.example(n=3,c_fraction=2)
        x,y,n=matched_snapshot(a,b,max_individuals=12)
        self.assertEqual(n,0)
        self.assertEqual(x.organisms,[])
        self.assertEqual(y.organisms,[])
        self.assertEqual(trace_composition(x,steps=8,reward=2,capacity=12,resources=1)['population'],0)


if __name__=='__main__':
    unittest.main()
