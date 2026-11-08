"""Behavioral tests of a genuinely new two-task conjunction holdout."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from organism_lab.digital_vm import COPY_REST, DIVIDE, NOP, TASK_A, TASK_B, execute_genome
from organism_lab.compositional_transfer_study import (
    FOUNDER, TaskGrammarWorld, novel_task_match, run_transfer, save_report, verify_report,
    holdout_composition,
)

class TransferStudyTests(unittest.TestCase):
    def test_composition_requires_both_functional_genes(self):
        self.assertTrue(novel_task_match((COPY_REST, TASK_A, TASK_B, DIVIDE)))
        self.assertFalse(novel_task_match((COPY_REST, TASK_A, NOP, DIVIDE)))
        self.assertFalse(novel_task_match((COPY_REST, TASK_B, TASK_B, DIVIDE)))
        self.assertFalse(novel_task_match((COPY_REST, TASK_A, COPY_REST, DIVIDE)))
        self.assertFalse(novel_task_match((TASK_A, TASK_B, DIVIDE)))

    def test_grammar_rejects_lethal_middle_opcodes_without_targeting_b(self):
        first=TaskGrammarWorld(seed=3, mutation_rate=1, initial_genome=FOUNDER, mode='task_grammar')
        second=TaskGrammarWorld(seed=3, mutation_rate=1, initial_genome=FOUNDER, mode='task_grammar')
        children=[first._mutate(FOUNDER) for _ in range(60)]
        assert children == [second._mutate(FOUNDER) for _ in range(60)]
        for genome in children:
            self.assertEqual(genome[0], COPY_REST)
            self.assertEqual(genome[-1], DIVIDE)
            self.assertTrue(set(genome[1:-1]) <= {NOP, TASK_A, TASK_B})
            self.assertEqual(execute_genome(genome), genome)
        self.assertIn((COPY_REST,TASK_A,TASK_B,DIVIDE),children)

    def test_frozen_unseen_task_holdout_is_reward_causal_and_input_immutable(self):
        world=TaskGrammarWorld(seed=9,mutation_rate=0,initial_genome=FOUNDER,mode='task_grammar',resources_per_tick=2)
        world.organisms=[type(world.organisms[0])(0,None,0,9,(COPY_REST,TASK_A,TASK_B,DIVIDE))]
        before=copy.deepcopy(world)
        rewarded=holdout_composition(world,steps=10,reward=3)
        control=holdout_composition(world,steps=10,reward=0)
        self.assertEqual(world.metrics(),before.metrics())
        self.assertEqual(world.organisms,before.organisms)
        self.assertGreater(rewarded['population'],control['population'])
        self.assertGreater(rewarded['births_added'],0)
        self.assertEqual(control['rewarded_steps'],0)

    def test_holdout_normalizes_cached_training_energy_before_novel_challenge(self):
        world=TaskGrammarWorld(seed=4,mutation_rate=0,initial_genome=FOUNDER,mode='task_grammar',
                               resources_per_tick=1,capacity=24)
        founder=type(world.organisms[0]);
        world.organisms=[founder(i,None,0,100,(COPY_REST,TASK_A,TASK_B,DIVIDE) if i<6
                                else (COPY_REST,TASK_B,NOP,DIVIDE)) for i in range(12)]
        rewarded=holdout_composition(world,steps=20,reward=2)
        null=holdout_composition(world,steps=20,reward=0)
        self.assertGreater(rewarded['population'],null['population'])
        self.assertLessEqual(null['population'],1)  # one resource-fed founder may persist
        self.assertTrue(all(x.energy==100 for x in world.organisms))

    def test_paired_experiment_has_controls_and_bounds(self):
        params=dict(seeds=tuple(range(20)),steps=55,shift_tick=18,holdout_steps=7,
                    capacity=20,resources=1,mutation_rate=.12)
        r=run_transfer(**params)
        self.assertEqual(r,run_transfer(**params))
        self.assertEqual(len(r['trials']),20*5)
        self.assertEqual(len(r['design']['arms']),5)
        self.assertTrue(r['negative_controls']['no_division_births_zero'])
        self.assertTrue(r['negative_controls']['no_mutation_novel_task_zero'])
        self.assertTrue(r['negative_controls']['grammar_all_functional'])
        for row in r['trials']:
            f=row['final']
            self.assertEqual(f['population'],1+f['births']-f['deaths'])
            self.assertLessEqual(f['population'],20)
            self.assertGreaterEqual(row['composition_holdout']['population'],0)
        self.assertEqual(sum(r['positive_seeds'] + r['negative_seeds'] + r['tied_seeds'] for _ in [0]),20)
        self.assertIn('not rewarded',r['design']['novel_task_definition'])

    def test_mutation_zero_cannot_create_conjunction(self):
        r=run_transfer(seeds=tuple(range(20)),steps=35,shift_tick=12,holdout_steps=5,
                       capacity=12,resources=1,mutation_rate=0)
        self.assertFalse(r['generalization_demonstrated'])
        self.assertTrue(all(x['novel_task_carriers']==0 for x in r['trials']))

    def test_input_guardrails(self):
        good=dict(seeds=tuple(range(20)),steps=35,shift_tick=10)
        bad=[dict(seeds=(0,)*20),dict(seeds=tuple(range(19))),dict(steps=301),
             dict(shift_tick=35),dict(capacity=257),dict(resources=-1),
             dict(mutation_rate=1.1),dict(holdout_steps=100)]
        for item in bad:
            with self.subTest(item=item),self.assertRaises(ValueError):
                run_transfer(**{**good,**item})

    def test_report_hash_replay_idempotence_and_tampering(self):
        r=run_transfer(seeds=tuple(range(20)),steps=35,shift_tick=10,
                       holdout_steps=4,capacity=12,resources=2)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'results'/'report.json'
            original=save_report(r,p)
            data=p.read_bytes()
            self.assertEqual(verify_report(p),original)
            self.assertEqual(save_report(r,p),original)
            self.assertEqual(p.read_bytes(),data)
            poisoned=json.loads(data)
            poisoned['report']['trials'][0]['final']['population']=1000
            p.write_text(json.dumps(poisoned))
            with self.assertRaisesRegex(ValueError,'digest'):
                verify_report(p)
            from organism_lab.compositional_transfer_study import _encode
            import hashlib
            poisoned['sha256']=hashlib.sha256(_encode(poisoned['report'])).hexdigest()
            p.write_text(json.dumps(poisoned))
            with self.assertRaisesRegex(ValueError,'replay'):
                verify_report(p)
            p.write_bytes(data)
            self.assertEqual(verify_report(p),original)

if __name__ == '__main__': unittest.main()
