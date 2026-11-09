"""Tests for non-seeded AB genotype mutation in bounded digital VM."""
import unittest
from organism_lab.digital_vm import COPY_REST, DIVIDE, NOP, TASK_A, TASK_B, execute_genome
from organism_lab.resource_competition import FOUNDER_GENOMES
from organism_lab.spontaneous_adaptation import DiscoveryWorld

class SpontaneousAdaptationTests(unittest.TestCase):
    def test_founders_contain_no_AB_and_valid_genomes(self):
        world=DiscoveryWorld(seed=1001,policy='eligible',mutation_rate=.08)
        self.assertEqual(len(world.organisms),12)
        self.assertEqual(sum(o.genome==FOUNDER_GENOMES['AB'] for o in world.organisms),0)
        self.assertEqual(sum(o.genome==FOUNDER_GENOMES['A'] for o in world.organisms),6)
        self.assertEqual(sum(o.genome==FOUNDER_GENOMES['B'] for o in world.organisms),6)
        self.assertTrue(all(execute_genome(o.genome)==o.genome for o in world.organisms))

    def test_mid_locus_mutations_remain_viable_and_can_create_AB_without_targeting(self):
        world=DiscoveryWorld(seed=1001,policy='eligible',mutation_rate=1)
        source=FOUNDER_GENOMES['A']
        mutants=[world._mutate(source) for _ in range(120)]
        self.assertTrue(all(x[0]==COPY_REST and x[-1]==DIVIDE for x in mutants))
        self.assertTrue(all(x[1] in (NOP,TASK_A,TASK_B) and x[2] in (NOP,TASK_A,TASK_B) for x in mutants))
        self.assertTrue(all(execute_genome(x)==x for x in mutants))
        self.assertIn(FOUNDER_GENOMES['AB'],mutants)

    def test_zero_mutation_identical_and_zero_division_never_birth(self):
        mutant_off=DiscoveryWorld(seed=1002,policy='eligible',mutation_rate=0)
        for tick in range(1,40):
            mutant_off.set_environment(TASK_A if ((tick-1)//12)%2==0 else TASK_B)
            mutant_off.step()
        self.assertEqual(mutant_off.mutation_events,0)
        self.assertEqual(mutant_off.ab_mutation_births,0)
        self.assertTrue(all(o.genome!=FOUNDER_GENOMES['AB'] for o in mutant_off.organisms))
        division_off=DiscoveryWorld(seed=1002,policy='eligible',mutation_rate=.08,allow_replication=False)
        for tick in range(1,40):
            division_off.set_environment(TASK_A if ((tick-1)//12)%2==0 else TASK_B)
            division_off.step()
        self.assertEqual(division_off.births,0)

if __name__=='__main__':unittest.main()

class PairedStudyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from organism_lab.spontaneous_adaptation import run_study
        cls.out=run_study(seeds=tuple(range(1200,1220)),steps=40,holdout_steps=5)

    def test_controls_and_bounded_trial_shapes(self):
        o=self.out
        self.assertEqual(len(o['trials']),20*5)
        self.assertTrue(all(o['negative_controls'].values()))
        for r in o['trials']:
            self.assertEqual(len(r['population_trace']),41)
            self.assertLessEqual(r['final_population'],12)
            self.assertEqual(r['final_population'],12+r['total_births']-r['deaths'])

    def test_reproducibility_and_fail_closed_params(self):
        from organism_lab.spontaneous_adaptation import run_study
        self.assertEqual(self.out,run_study(seeds=tuple(range(1200,1220)),steps=40,holdout_steps=5))
        for options in ({'seeds':tuple(range(19))},{'seeds':[1200]*20},
                        {'steps':True},{'period':0},{'mutation_rate':True},
                        {'holdout_steps':55}):
            with self.subTest(options=options),self.assertRaises(ValueError):
                run_study(**options)

    def test_readback_idempotence_detects_forged_digest(self):
        import tempfile,json,hashlib
        from pathlib import Path
        from organism_lab.spontaneous_adaptation import save_report,verify_report,_encode
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'data'/'report.json'
            x=save_report(self.out,p)
            b=p.read_bytes()
            self.assertEqual(verify_report(p),x)
            self.assertEqual(save_report(self.out,p),x)
            self.assertEqual(p.read_bytes(),b)
            forged=json.loads(b)
            forged['report']['trials'][0]['ab_mutation_births']=123
            p.write_text(json.dumps(forged))
            with self.assertRaisesRegex(ValueError,'digest'):verify_report(p)
            forged['sha256']=hashlib.sha256(_encode(forged['report'])).hexdigest()
            p.write_text(json.dumps(forged))
            with self.assertRaisesRegex(ValueError,'recomputation'):verify_report(p)
