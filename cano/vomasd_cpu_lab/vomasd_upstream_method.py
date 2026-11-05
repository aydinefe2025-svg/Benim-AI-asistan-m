"""Exact method snippet copied from pinned upstream VOMASDHierPolicy source.

Original: https://github.com/LucasCJYSDL/VOMASD
Path: VO-MASD/onpolicy/algorithms/vomasd/vomasd_hier_policy.py
Git blob: 621980122d13f1c8dab31c4ccabe9f5c4099c95f
MIT licensed; copyright (c) 2024 Jiayu Chen.

Only the class wrapper is new.  The forward_codebook function itself is
untouched, apart from being embedded in this dependency-free CPU harness.
"""
import torch


class VOMASDHierPolicyOriginalMethod:
    def __init__(self, top_weights, bottom_weights):
        self.skill_dim = top_weights.shape[1]
        self.top_skill_num = top_weights.shape[0]
        self.skill_num = bottom_weights.shape[0]
        self.top_codebook = torch.nn.Embedding.from_pretrained(top_weights.clone(), freeze=False)
        self.btm_codebook = torch.nn.Embedding.from_pretrained(bottom_weights.clone(), freeze=False)

    def forward_codebook(self, z_e, is_top):
        def _code_match(z_e, codebook, skill_num):
            z_e_flattened = z_e.reshape(-1, self.skill_dim)
            d = torch.sum(z_e_flattened ** 2, dim=1, keepdim=True) + \
                torch.sum(codebook.weight**2, dim=1) - 2 * \
                torch.matmul(z_e_flattened, codebook.weight.t())
            # print("4: ", d.shape) # torch.Size([384, 5])
            # find closest encodings
            min_encoding_indices = torch.argmin(d, dim=1).unsqueeze(1)
            min_encodings = torch.zeros(min_encoding_indices.shape[0], skill_num).to(z_e.device)
            # print("5: ", min_encodings.shape, min_encoding_indices.shape, min_encoding_indices) # torch.Size([384, 5]) torch.Size([384, 1])
            min_encodings.scatter_(1, min_encoding_indices, 1)
            # print("6 ", min_encodings.shape, min_encodings) # torch.Size([384, 5])
            # get quantized latent vectors
            z_q = torch.matmul(min_encodings, codebook.weight).view(z_e.shape)
            return z_q
        
        if is_top:
            return _code_match(z_e, self.top_codebook, self.top_skill_num)
        return _code_match(z_e, self.btm_codebook, self.skill_num)
    
    
