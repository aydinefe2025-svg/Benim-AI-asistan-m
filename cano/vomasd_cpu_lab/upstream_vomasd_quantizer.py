"""Isolated source-faithful adaptation of VO-MASD Hier's forward_codebook.

Upstream: LucasCJYSDL/VOMASD, MIT license, blob
621980122d13f1c8dab31c4ccabe9f5c4099c95f
VO-MASD/onpolicy/algorithms/vomasd/vomasd_hier_policy.py

The method below preserves upstream's nearest-neighbor/one-hot/matmul logic.
Only class construction has been reduced so it can run on CPU without SMAC.
This module DOES NOT instantiate VO-MASD's autoencoder, grouper or MARL learner.
"""
import torch


class IsolatedVOMASDHierCodebook:
    def __init__(self, top_weights: torch.Tensor, bottom_weights: torch.Tensor):
        if top_weights.ndim != 2 or bottom_weights.ndim != 2:
            raise ValueError('codebooks must be 2-D')
        if top_weights.shape[1] != bottom_weights.shape[1]:
            raise ValueError('top and bottom embedding dimensions must match')
        self.skill_dim = top_weights.shape[1]
        self.top_skill_num = top_weights.shape[0]
        self.skill_num = bottom_weights.shape[0]
        self.top_codebook = torch.nn.Embedding.from_pretrained(top_weights.clone(), freeze=False)
        self.btm_codebook = torch.nn.Embedding.from_pretrained(bottom_weights.clone(), freeze=False)

    def forward_codebook(self, z_e, is_top):
        # Mathematical core transcribed from upstream VOMASDHierPolicy.forward_codebook.
        def _code_match(z_e, codebook, skill_num):
            z_e_flattened = z_e.reshape(-1, self.skill_dim)
            d = torch.sum(z_e_flattened ** 2, dim=1, keepdim=True) + \
                torch.sum(codebook.weight**2, dim=1) - 2 * \
                torch.matmul(z_e_flattened, codebook.weight.t())
            min_encoding_indices = torch.argmin(d, dim=1).unsqueeze(1)
            min_encodings = torch.zeros(min_encoding_indices.shape[0], skill_num).to(z_e.device)
            min_encodings.scatter_(1, min_encoding_indices, 1)
            z_q = torch.matmul(min_encodings, codebook.weight).view(z_e.shape)
            return z_q

        if is_top:
            return _code_match(z_e, self.top_codebook, self.top_skill_num)
        return _code_match(z_e, self.btm_codebook, self.skill_num)
