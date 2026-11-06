"""Controlled sensitivity diagnosis for upstream-initialized hierarchical codebooks.
This is *not* a SMAC win-rate or scientific performance reproduction.
"""
import unittest
import torch
from group_sensitivity import run, PARTITIONS
from controlled_groups import NativeHierarchyHarness
from native_parity import verify_method_provenance


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)

    def test_upstream_codebook_source_hash(self):
        self.assertTrue(verify_method_provenance())

    def test_four_different_group_partitions_are_distinct(self):
        self.assertEqual(len(PARTITIONS),4)
        self.assertEqual(len(set(PARTITIONS)),4)

    def test_default_init_32_seeds_no_quantized_group_difference(self):
        r=run()
        self.assertEqual(r['seeds'],32)
        self.assertEqual(r['cases'],128)
        self.assertEqual(r['fraction_seeds_with_output_change'],0)
        self.assertEqual(r['median_top_code_utilization'],1)

    def test_group_encoder_is_sensitive_but_quantization_collapses(self):
        r=run(seeds=[0])['rows'][0]
        self.assertGreater(r['max_group_encoder_latent_change'],0)
        self.assertEqual(r['max_output_change_vs_three_alternative_partitions'],0)
        self.assertEqual(r['distinct_quantized_top_codes'],1)

    def test_positive_control_scaled_head_changes_group_output(self):
        seed=7
        net=NativeHierarchyHarness(seed=seed)
        # This intentionally *changes* weights; not a trained/published model.
        with torch.no_grad(): net.top_skill_encoder.head.weight.mul_(10000)
        torch.manual_seed(seed)
        states=torch.randn(2,3,3,2)
        latent=torch.randn(2,3,3,4)
        outs=[]
        with torch.no_grad():
            for partition in (PARTITIONS[0], PARTITIONS[-1]):
                net.grouper.partition=partition
                outs.append(net.forward_code(states,latent,'controlled_marl_fixture',True)[0])
        self.assertGreater((outs[0]-outs[1]).abs().max().item(),.001)

    def test_data_source_is_explicitly_synthetic(self):
        r=run(seeds=[5])
        self.assertFalse(r['upstream_learner_executed'])
        self.assertFalse(r['sc2_executed'])
        self.assertFalse(r['paper_results_replicated'])


if __name__=='__main__':unittest.main()
