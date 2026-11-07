"""Tests for a measured, bounded fitness audit; no actual biological or LLM evolution."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.adaptation_validation import (
    ARMS, FOUNDER, _functional_b, _serialize, _trial,
    run_validation, save_and_verify, verify_report,
)
from organism_lab.digital_vm import COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld, execute_genome


class AdaptationValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = run_validation(seeds=tuple(range(20)), steps=60, shift_tick=20,
                                    holdout_steps=8, capacity=24, resources=2)

    def test_reproducible_paired_three_arms_and_population_bounds(self):
        p = self.report
        self.assertEqual(p, run_validation(seeds=tuple(range(20)), steps=60,
                            shift_tick=20, holdout_steps=8, capacity=24, resources=2))
        self.assertEqual(len(p['trials']), 20*3)
        self.assertEqual(p['design']['arms'], list(ARMS))
        for trial in p['trials']:
            self.assertLessEqual(trial['final']['population'], 24)
            self.assertGreaterEqual(trial['final']['population'], 0)
            self.assertEqual(trial['final']['population'],
                             1+trial['final']['births']-trial['final']['deaths'])
            self.assertEqual(sum(v['population'] for v in trial['cohorts'].values()),
                             trial['final']['population'])

    def test_negative_controls_and_true_inherited_mutation(self):
        p=self.report
        self.assertTrue(p['negative_control_births_zero'])
        self.assertTrue(all(t['final']['births']==0 for t in p['trials'] if t['arm']=='no_division'))
        self.assertTrue(all(t['final']['unique_genomes']==1 for t in p['trials'] if t['arm']=='no_mutation'))
        self.assertTrue(any(t['final']['unique_genomes']>1 for t in p['trials'] if t['arm']=='mutation'))
        self.assertTrue(any(t['functional_task_b']>0 for t in p['trials'] if t['arm']=='mutation'))
        # TASK_B in a nonreplicating genome is not viable inherited task functionality.
        class Dummy:
            organisms=[type('O',(),{'genome':(TASK_B,DIVIDE)})()]
        self.assertEqual(_functional_b(Dummy()),0)
        self.assertIsNone(execute_genome((TASK_B,DIVIDE)))

    def test_holdout_is_frozen_genotype_perturbation(self):
        p=self.report
        self.assertEqual(p['design']['holdout_steps'],8)
        self.assertIn('8 ticks',p['design']['holdout'])
        self.assertIn('not a previously unseen task',p['limits'][2])
        self.assertEqual(len(p['paired_holdout_population_gain'].keys()),5)
        self.assertEqual(p['paired_functional_b_gain']['n'],20)
        self.assertGreaterEqual(p['exact_one_sided_sign_p'],0)
        self.assertLessEqual(p['exact_one_sided_sign_p'],1)
        self.assertEqual(p['positive_functional_b_seeds'] + p['negative_functional_b_seeds'] + p['tied_functional_b_seeds'],20)

    def test_mutation_rate_zero_eliminates_diversity_claim(self):
        p=run_validation(seeds=tuple(range(20)),steps=30,shift_tick=10,
                         holdout_steps=5,capacity=16,resources=2,mutation_rate=0)
        self.assertFalse(p['adaptation_demonstrated'])
        self.assertEqual(p['mean_unique_genomes_gain'],0)
        self.assertEqual(p['paired_functional_b_gain']['mean'],0)
        self.assertEqual(p['paired_holdout_population_gain']['mean'],0)

    def test_seed_mutation_and_parent_lineage_reproducible(self):
        def evolve():
            w=GenomeWorld(seed=4,capacity=24,resources_per_tick=2,mutation_rate=.2,
                          initial_genome=FOUNDER,environment=TASK_A,task_reward=2)
            known={0:FOUNDER}
            for tick in range(40):
                if tick==12:w.set_environment(TASK_B)
                w.step()
                for o in w.organisms:
                    if o.identifier not in known:
                        self.assertIn(o.parent,known)
                        self.assertGreater(o.generation,0)
                        self.assertEqual(len(o.genome),len(known[o.parent]))
                        known[o.identifier]=o.genome
            return w.metrics(),known
        self.assertEqual(evolve(),evolve())
        self.assertGreater(len(evolve()[1]),1)

    def test_invalid_parameters_and_duplicate_seeds_fail(self):
        examples=[{'seeds':tuple(range(19))}, {'seeds':(0,)*20},
                  {'seeds':tuple(range(20)),'steps':1000},
                  {'seeds':tuple(range(20)),'shift_tick':120},
                  {'seeds':tuple(range(20)),'capacity':10000},
                  {'seeds':tuple(range(20)),'mutation_rate':True},
                  {'seeds':tuple(range(20)),'holdout_steps':100}]
        for options in examples:
            with self.subTest(options=options),self.assertRaises(ValueError):
                run_validation(**options)

    def test_readback_replay_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'deep'/'study.json'
            first=save_and_verify(self.report,path)
            data=path.read_bytes()
            self.assertEqual(verify_report(path),first)
            self.assertEqual(save_and_verify(self.report,path),first)
            self.assertEqual(path.read_bytes(),data)
            self.assertFalse(path.with_name('.study.json.tmp').exists())
            conflicting=run_validation(seeds=tuple(range(20)),steps=61,shift_tick=20,
                                        holdout_steps=8,capacity=24,resources=2)
            with self.assertRaises(FileExistsError):
                save_and_verify(conflicting,path)
            self.assertEqual(path.read_bytes(),data)

    def test_detects_both_raw_tamper_and_forged_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'study.json'
            save_and_verify(self.report,path)
            clean=json.loads(path.read_text(encoding='utf-8'))
            changed=json.loads(path.read_text(encoding='utf-8'))
            changed['report']['trials'][0]['final']['births']=900
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'digest'):
                verify_report(path)
            changed['sha256']=hashlib.sha256(_serialize(changed['report'])).hexdigest()
            path.write_text(json.dumps(changed),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'recomputation'):
                verify_report(path)
            path.write_text(json.dumps(clean),encoding='utf-8')
            self.assertEqual(verify_report(path),clean)


if __name__=='__main__':
    unittest.main()