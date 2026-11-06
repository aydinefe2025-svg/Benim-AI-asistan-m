"""Source-adapted original VO-MASD-Hier forward_code with deterministic grouping.
These are *component tests* using a controlled Grouper fixture, NOT SMAC.
"""
import math
import unittest
import torch
from controlled_groups import FixtureGrouper, NativeHierarchyHarness, evaluate
from native_hierarchy import NativeHierarchyForwardMixin
from original_top_skill_components import TopSkillEncoder


class HierarchyTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(33)
        self.net = NativeHierarchyHarness(seed=33)
        self.states = torch.randn(2,3,3,2)
        self.latent = torch.randn(2,3,3,4,requires_grad=True)

    def test_source_forward_method_bound(self):
        self.assertIs(NativeHierarchyHarness.forward_code, NativeHierarchyForwardMixin.forward_code)

    def test_real_top_encoder_is_instantiated(self):
        self.assertIsInstance(self.net.top_skill_encoder, TopSkillEncoder)
        self.assertGreater(sum(p.numel() for p in self.net.top_skill_encoder.parameters()),0)

    def test_full_shape_contract(self):
        z,top,btm,group,log,val,reward=self.net.forward_code(self.states,self.latent,'controlled_marl_fixture',False)
        self.assertEqual(tuple(z.shape),(2,3,3,8))
        self.assertEqual(tuple(top.shape),(6,3,1))
        self.assertEqual(tuple(btm.shape),(6,3,1))
        self.assertEqual(tuple(reward.shape),(6,3,1))
        self.assertEqual(tuple(group.shape),(6,3,1))
        self.assertEqual(tuple(log.shape),(6,3,1))
        self.assertEqual(tuple(val.shape),(6,3,1))
        self.assertFalse(reward.requires_grad)

    def test_native_grouper_returns_flat_skill_embeddings(self):
        groups,skill,*_ = self.net.grouper(self.states,self.latent,'controlled_marl_fixture',False)
        self.assertEqual(tuple(skill.shape),(6,3,4))
        self.assertEqual(len(groups),6)
        self.assertEqual(tuple(groups[0][(0,1)].shape),(2,4))

    def test_gradients_reach_input_and_top_encoder_and_codebooks(self):
        z,top,btm,*_ = self.net.forward_code(self.states,self.latent,'controlled_marl_fixture',False)
        (z.square().mean()+top.mean()+btm.mean()).backward()
        self.assertIsNotNone(self.latent.grad)
        self.assertGreater(float(self.latent.grad.norm()),0)
        self.assertIsNotNone(self.net.top_codebook.weight.grad)
        self.assertIsNotNone(self.net.btm_codebook.weight.grad)
        self.assertIsNotNone(self.net.top_skill_encoder.head.weight.grad)
        self.assertTrue(torch.isfinite(self.net.top_skill_encoder.head.weight.grad).all())

    def test_second_stage_output_shape(self):
        z=self.net.forward_code(self.states,self.latent,'controlled_marl_fixture',True,second_stage=True)
        self.assertEqual(tuple(z.shape),(2,3,3,8))

    def test_explicit_unknown_task_fails(self):
        with self.assertRaisesRegex(ValueError,'fixture only'):
            self.net.forward_code(self.states,self.latent,'StarCraft2',True)

    def test_partitions_must_cover_exact_agent_set(self):
        for part in [((0,1),),((0,1),(1,2)),((),(0,1,2)),((0,4),(1,2))]:
            fixture=FixtureGrouper(part)
            with self.assertRaises(ValueError):
                fixture(self.states,self.latent,'controlled_marl_fixture',False)

    def test_single_group_three_singletons_and_noncontiguous(self):
        for part in [((0,1,2),),((0,),(1,),(2,)),((0,2),(1,))]:
            result=evaluate(42,part)
            self.assertTrue(result['finite'])
            self.assertEqual(result['z_shape'],[2,3,3,8])

    def test_replay_is_exact_on_cpu(self):
        self.assertEqual(evaluate(70),evaluate(70))

    def test_seed_changes_output(self):
        self.assertNotEqual(evaluate(70)['bottom_loss'],evaluate(71)['bottom_loss'])

    def test_top_and_bottom_are_finite(self):
        for seed in range(16):
            r=evaluate(seed)
            self.assertTrue(r['finite'])
            self.assertTrue(math.isfinite(r['grad_norm']))
            self.assertGreater(r['grad_norm'],0)
            self.assertGreater(r['param_grad_max'],0)
            self.assertFalse(r['full_paper_reproduction'])

    def test_wrong_embedding_dim_rejected(self):
        with self.assertRaises((RuntimeError,ValueError)):
            self.net.forward_code(self.states,torch.randn(2,3,3,5),'controlled_marl_fixture',False)

    def test_group_assignment_for_noncontiguous_agents(self):
        fixture=FixtureGrouper(((0,2),(1,)))
        _,_,indices,*_=fixture(self.states,self.latent,'controlled_marl_fixture',True)
        self.assertEqual(indices[0,:,0].tolist(),[0,1,0])

    def test_parameter_update_after_backward(self):
        before=self.net.top_skill_encoder.head.weight.detach().clone()
        opt=torch.optim.SGD(self.net.parameters(),lr=.001)
        z,top,btm,*_=self.net.forward_code(self.states,self.latent,'controlled_marl_fixture',False)
        loss=z.square().mean()+top.mean()+btm.mean()
        opt.zero_grad();loss.backward();opt.step()
        self.assertFalse(torch.equal(before,self.net.top_skill_encoder.head.weight))

    def test_no_sc2_import(self):
        import sys
        self.assertNotIn('smac',sys.modules)
        self.assertNotIn('pysc2',sys.modules)


if __name__=='__main__':
    unittest.main()
