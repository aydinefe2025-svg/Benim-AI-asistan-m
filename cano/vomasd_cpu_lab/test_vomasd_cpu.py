import unittest
import hashlib
import torch
from upstream_vomasd_quantizer import IsolatedVOMASDHierCodebook
from toy_quantizer import experiment
from preflight import inspect_shell_script
from pathlib import Path

ORIGINAL=Path(__file__).with_name('train_marine_upstream.sh').read_text()

class QuantizerRegression(unittest.TestCase):
    def test_nearest_code_reference_top(self):
        q=IsolatedVOMASDHierCodebook(torch.tensor([[0.,0.],[2.,2.]]), torch.tensor([[1.,1.],[3.,3.]]))
        v=torch.tensor([[.1,.1],[1.9,2.1]])
        result=q.forward_codebook(v,True)
        self.assertTrue(torch.allclose(result, torch.tensor([[0.,0.],[2.,2.]])))
        self.assertTrue(torch.allclose(result, q.top_codebook.weight[torch.cdist(v,q.top_codebook.weight).argmin(dim=1)]))

    def test_nearest_code_reference_bottom(self):
        q=IsolatedVOMASDHierCodebook(torch.tensor([[0.,0.],[2.,2.]]), torch.tensor([[1.,1.],[3.,3.]]))
        self.assertTrue(torch.allclose(q.forward_codebook(torch.tensor([[2.8,3.0]]),False),torch.tensor([[3.,3.]])))

    def test_batch_shape_preserved(self):
        q=IsolatedVOMASDHierCodebook(torch.randn(8,5),torch.randn(6,5))
        v=torch.randn(2,3,4,5)
        self.assertEqual(q.forward_codebook(v, True).shape, v.shape)
        self.assertEqual(q.forward_codebook(v, False).shape, v.shape)

    def test_gradient_reaches_codebook(self):
        q=IsolatedVOMASDHierCodebook(torch.tensor([[0.,0.],[3.,3.]]), torch.tensor([[2.,2.]]))
        z=torch.tensor([[1.,1.],[2.8,3.1]],requires_grad=True)
        loss=(q.forward_codebook(z,True)-z).square().mean()
        loss.backward()
        self.assertIsNotNone(q.top_codebook.weight.grad)
        self.assertTrue(bool(torch.isfinite(q.top_codebook.weight.grad).all()))
        self.assertGreater(float(q.top_codebook.weight.grad.abs().sum()),0)

    def test_upstream_launcher_blob_identity(self):
        data=Path(__file__).with_name('train_marine_upstream.sh').read_bytes()
        blob=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        self.assertEqual(blob,'40e9a621e7dd89fef427504da4959fcd4db7ae8f')

    def test_canonical_source_blocked_baseline(self):
        d=inspect_shell_script(ORIGINAL)
        self.assertEqual(d['selected_algorithm'],'odis')
        self.assertEqual(d['status'],'BLOCKED_WRONG_ALGORITHM')
        self.assertEqual(d['num_env_steps'],8000000)
        self.assertEqual(d['device_pin'],['3'])

    def test_unbounded_vo_command_blocked(self):
        d=inspect_shell_script(ORIGINAL.replace('algo="odis"','algo="vomasd-hier"'))
        self.assertEqual(d['status'],'BLOCKED_RESOURCE_BUDGET')

    def test_small_vo_preflight_still_not_execution(self):
        d=inspect_shell_script(ORIGINAL.replace('algo="odis"','algo="vomasd-3d"').replace('8000000','1000'))
        self.assertEqual(d['status'],'READY_FOR_MANUAL_ENVIRONMENT_REVIEW')
        self.assertFalse(d['training_executed'])

    def test_forged_shell_mode_rejected(self):
        with self.assertRaises(ValueError):
            inspect_shell_script(ORIGINAL.replace('algo="odis"','algo="evil-command"'))

    def test_duplicate_algo_declaration_rejected(self):
        with self.assertRaises(ValueError):
            inspect_shell_script(ORIGINAL+'\nalgo="vomasd-hier"\n')

    def test_synthetic_learning_improves_holdout(self):
        z=experiment()
        self.assertGreater(z['heldout_mse_start'],z['heldout_mse_end']*2)
        self.assertEqual(z['distinct_codes_used_on_holdout'],4)
        self.assertFalse(z['paper_result_replicated'])

    def test_deterministic_seed(self):
        x,y=experiment(),experiment()
        self.assertEqual(x,y)

if __name__=='__main__':unittest.main()
