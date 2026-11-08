"""Independent regression gates for bounded 4-arm digital genotype comparison."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.core_protection_study import (
    ARMS, FOUNDER, CoreProtectedWorld, _encode, run_study, save_report, verify_report,
)
from organism_lab.digital_vm import COPY_REST, DIVIDE, TASK_A, TASK_B, GenomeWorld, execute_genome


class CoreProtectionStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.study = run_study(seeds=tuple(range(20)), steps=40, shift_tick=12,
                              capacity=24, resources=2, holdout_steps=8)

    def test_same_mutation_proposals_no_task_targeting(self):
        for seed in range(100):
            base = GenomeWorld(seed=seed, mutation_rate=.37, initial_genome=FOUNDER)
            guard = CoreProtectedWorld(seed=seed, mutation_rate=.37, initial_genome=FOUNDER)
            for _ in range(30):
                raw = base._mutate(FOUNDER)
                protected = guard._mutate(FOUNDER)
                self.assertEqual(raw[1], protected[1])
                self.assertEqual(protected[0], COPY_REST)
                self.assertEqual(protected[2], DIVIDE)
                # Core protection does not guarantee viability: a second COPY_REST at the task locus may over-copy.
        self.assertIsNone(execute_genome((COPY_REST, COPY_REST, DIVIDE)))
        with self.assertRaises(ValueError):
            guard._mutate((TASK_A, TASK_A, DIVIDE))

    def test_zero_mutation_preserves_parent_and_children(self):
        base = GenomeWorld(seed=9, mutation_rate=0, initial_genome=FOUNDER)
        protected = CoreProtectedWorld(seed=9, mutation_rate=0, initial_genome=FOUNDER)
        for _ in range(35):
            self.assertEqual(base.step(), protected.step())
            self.assertEqual(base.organisms, protected.organisms)
        self.assertTrue(all(o.genome == FOUNDER for o in protected.organisms))

    def test_bounded_paired_design_negative_controls(self):
        r=self.study
        self.assertEqual(r['design']['arms'],list(ARMS))
        self.assertEqual(len(r['trials']),80)
        self.assertTrue(r['no_division_births_zero'])
        self.assertTrue(r['no_mutation_functional_b_zero'])
        self.assertFalse(r['robust_improvement_demonstrated'])
        for row in r['trials']:
            m=row['final']
            self.assertEqual(m['population'],1+m['births']-m['deaths'])
            self.assertLessEqual(m['population'],24)
            self.assertGreaterEqual(row['functional_b_share'],0)
            self.assertLessEqual(row['functional_b_share'],1)
            if row['arm']=='protected_core':
                self.assertTrue(all(g[0]==COPY_REST and g[-1]==DIVIDE
                                    for g in row['distinct_genomes']))
                self.assertIn(row['viable_replicator_share'],(0.0,1.0))

    def test_reproducible_same_seeds_and_strict_gate(self):
        args=dict(seeds=tuple(range(20)),steps=40,shift_tick=12,
                  capacity=24,resources=2,holdout_steps=8)
        self.assertEqual(run_study(**args),self.study)
        r=self.study
        self.assertEqual(r['positive_seeds']+r['negative_seeds']+r['tied_seeds'],20)
        self.assertEqual(r['paired_functional_b_gain']['n'],20)
        self.assertGreaterEqual(r['exact_one_sided_sign_p'],0)
        self.assertLessEqual(r['exact_one_sided_sign_p'],1)

    def test_invalid_inputs_fail_closed(self):
        scenarios=(dict(seeds=tuple(range(19))),dict(seeds=(0,)*20),
                   dict(steps=301),dict(shift_tick=120),dict(capacity=1000),
                   dict(resources=-1),dict(mutation_rate=True),dict(holdout_steps=51))
        for opts in scenarios:
            with self.subTest(opts=opts),self.assertRaises(ValueError):
                run_study(**opts)

    def test_saved_report_idempotent_and_independent_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'nested'/'study.json'
            first=save_report(self.study,path)
            original=path.read_bytes()
            self.assertEqual(verify_report(path),first)
            self.assertEqual(save_report(self.study,path),first)
            self.assertEqual(path.read_bytes(),original)
            conflict=run_study(seeds=tuple(range(20)),steps=41,shift_tick=12,
                               capacity=24,resources=2,holdout_steps=8)
            with self.assertRaises(FileExistsError):
                save_report(conflict,path)
            self.assertEqual(path.read_bytes(),original)

    def test_tamper_and_forged_hash_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'study.json'
            good=save_report(self.study,path)
            corrupt=json.loads(path.read_text())
            corrupt['report']['trials'][0]['final']['births']=999
            path.write_text(json.dumps(corrupt))
            with self.assertRaisesRegex(ValueError,'digest'):
                verify_report(path)
            corrupt['sha256']=hashlib.sha256(_encode(corrupt['report'])).hexdigest()
            path.write_text(json.dumps(corrupt))
            with self.assertRaisesRegex(ValueError,'recomputation'):
                verify_report(path)
            path.write_bytes(_encode(good))
            self.assertEqual(verify_report(path),good)

    def test_original_vm_unchanged_and_replicates(self):
        w=GenomeWorld(seed=3,capacity=8,resources_per_tick=12,
                      mutation_rate=1,initial_genome=FOUNDER)
        for _ in range(20):w.step()
        self.assertGreater(w.births,0)
        # Non-viable descendants are allowed only in the untreated original VM.
        self.assertTrue(any(execute_genome(o.genome) is None for o in w.organisms))

if __name__=='__main__':
    unittest.main()