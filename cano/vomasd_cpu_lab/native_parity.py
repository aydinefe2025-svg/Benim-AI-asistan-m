"""Independent native-vs-transcribed VO-MASD hierarchical codebook parity audit.

This executes the upstream original `forward_codebook` method (byte-for-byte
extracted from pinned upstream blob) in a minimal dependency-free class wrapper,
without importing any StarCraft/SMAC dependencies or claiming whole-paper results.
"""
import hashlib
import json
from pathlib import Path

import torch
from upstream_vomasd_quantizer import IsolatedVOMASDHierCodebook
from vomasd_upstream_method import VOMASDHierPolicyOriginalMethod

PINNED_UPSTREAM_GIT_BLOB = '621980122d13f1c8dab31c4ccabe9f5c4099c95f'
# SHA-256 of the exact 1232-byte function snippet from original Github source.
METHOD_SHA256 = '1e98587e760bda07dd0c08699fa912cbc4adab115decb483f048f1fca263c680'


def original_method_source():
    content = Path(__file__).with_name('vomasd_upstream_method.py').read_bytes()
    token = b'    def forward_codebook('
    start = content.index(token)
    return content[start:]


def verify_method_provenance():
    data = original_method_source()
    if len(data) != 1232:
        raise ValueError('upstream source method changed (byte length)')
    if hashlib.sha256(data).hexdigest() != METHOD_SHA256:
        raise ValueError('upstream source method changed (SHA-256)')
    return True


def run_parity(seeds=range(16), *, n_agents=3, latent_dim=4):
    """Check both codebook choices, values, and gradients using shared test inputs.

    Gradients are expected to be exact or numerically near-identical in float32. This does
    NOT measure multi-agent win-rate, quality of grouping, or scientific claims.
    """
    verify_method_provenance()
    results=[]
    for seed in seeds:
        torch.manual_seed(seed)
        top = torch.randn(7, latent_dim, dtype=torch.float32)
        bottom = torch.randn(9, latent_dim, dtype=torch.float32)
        x = torch.randn(2, 5, n_agents, latent_dim, dtype=torch.float32)
        upstream = VOMASDHierPolicyOriginalMethod(top, bottom)
        adaptation = IsolatedVOMASDHierCodebook(top, bottom)
        for is_top in (True, False):
            u_x=x.clone().detach().requires_grad_(True)
            a_x=x.clone().detach().requires_grad_(True)
            u=upstream.forward_codebook(u_x, is_top)
            a=adaptation.forward_codebook(a_x, is_top)
            value_err=(u-a).abs().max().item()
            # Differentiability of input is not guaranteed by source's discrete
            # argmin quantization; check only codebook gradients at a shared loss.
            u.square().mean().backward()
            a.square().mean().backward()
            u_w=(upstream.top_codebook if is_top else upstream.btm_codebook).weight.grad
            a_w=(adaptation.top_codebook if is_top else adaptation.btm_codebook).weight.grad
            grad_err=(u_w-a_w).abs().max().item()
            matches=bool(torch.allclose(u,a,atol=1e-12,rtol=1e-12))
            if not matches or not torch.allclose(u_w,a_w,atol=1e-12,rtol=1e-12):
                raise AssertionError(f'native/adapted parity failed seed={seed} top={is_top}: value={value_err}, gradient={grad_err}')
            results.append({'seed':seed,'is_top':is_top,'max_abs_output_diff':value_err,'max_abs_grad_diff':grad_err})
    return {
        'provenance':'LucasCJYSDL/VOMASD/VO-MASD/onpolicy/algorithms/vomasd/vomasd_hier_policy.py',
        'upstream_git_blob':PINNED_UPSTREAM_GIT_BLOB,
        'upstream_method_sha256':METHOD_SHA256,
        'native_original_function_executed':True,
        'sc2_smac_executed':False,
        'paper_experiment_reproduced':False,
        'synthetic_only':True,
        'parity_cases':len(results),
        'max_abs_output_diff':max(r['max_abs_output_diff'] for r in results),
        'max_abs_codebook_gradient_diff':max(r['max_abs_grad_diff'] for r in results),
        'results':results,
    }


if __name__ == '__main__':
    p=Path(__file__).resolve().parent/'native_parity_results.json'
    p.write_text(json.dumps(run_parity(),indent=2,sort_keys=True)+'\n')
    print(p.read_text())
