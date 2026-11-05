"""Regression tests for byte-pinned upstream method parity."""
import tempfile
import unittest
from unittest import mock
from pathlib import Path

import torch
from native_parity import run_parity, verify_method_provenance, original_method_source, METHOD_SHA256
from vomasd_upstream_method import VOMASDHierPolicyOriginalMethod
from upstream_vomasd_quantizer import IsolatedVOMASDHierCodebook


class NativeParityTests(unittest.TestCase):
    def test_upstream_source_is_byte_pinned(self):
        self.assertTrue(verify_method_provenance())
        self.assertEqual(len(original_method_source()), 1232)

    def test_falsified_method_is_rejected(self):
        with mock.patch('native_parity.original_method_source',return_value=b'def fake(): pass'):
            with self.assertRaises(ValueError): verify_method_provenance()

    def test_native_top_and_bottom_forward_parity(self):
        report=run_parity(seeds=range(3))
        self.assertEqual(report['parity_cases'],6)
        self.assertFalse(report['paper_experiment_reproduced'])
        self.assertLessEqual(report['max_abs_output_diff'],1e-12)

    def test_gradient_parity(self):
        report=run_parity(seeds=[7,9])
        self.assertLessEqual(report['max_abs_codebook_gradient_diff'],1e-12)

    def test_many_shapes_and_both_books(self):
        for dim in (1,4,8):
            for agents in (1,3,5):
                with self.subTest(dim=dim,agents=agents):
                    report=run_parity(seeds=[4],latent_dim=dim,n_agents=agents)
                    self.assertEqual(report['parity_cases'],2)

    def test_native_float64_known_limitation_fails_explicitly(self):
        weights=torch.zeros(2,3,dtype=torch.float64)
        native=VOMASDHierPolicyOriginalMethod(weights,weights)
        with self.assertRaisesRegex(RuntimeError,"same dtype"):
            native.forward_codebook(torch.zeros(1,3,dtype=torch.float64),True)

    def test_bad_shape_does_not_pretend_success(self):
        t=torch.zeros(3,3)
        native=VOMASDHierPolicyOriginalMethod(t,t)
        with self.assertRaises(RuntimeError):
            native.forward_codebook(torch.zeros(5,4),True)

    def test_comparison_model_values_are_not_globally_equal(self):
        native=VOMASDHierPolicyOriginalMethod(torch.tensor([[1.,1.],[3.,3.]]),torch.tensor([[2.,2.],[4.,4.]]))
        adapted=IsolatedVOMASDHierCodebook(torch.tensor([[1.,1.],[3.,3.]]),torch.tensor([[2.,2.],[4.,4.]]))
        a=native.forward_codebook(torch.tensor([[.5,.5]]),True)
        b=adapted.forward_codebook(torch.tensor([[.5,.5]]),True)
        self.assertTrue(torch.equal(a,b))
        self.assertFalse(torch.equal(a,native.forward_codebook(torch.tensor([[.5,.5]]),False)))


if __name__ == '__main__':
    unittest.main()
