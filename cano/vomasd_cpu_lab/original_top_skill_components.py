"""Upstream-equivalent TopSkillEncoder/LightEncodeBlock/SelfAttention code.
Source: LucasCJYSDL/VOMASD upstream files pinned to commit
ff05a1f2bebd1ed8c1a49afc424bac8905eb4de3 (MIT license).
Only independent imports and init helpers are consolidated for isolated CPU use.
No original Grouper, MARL policy or SC2 runtime is included.
"""
import math
import torch
import torch.nn as nn
import torch.nn.functional as F


def init(module, weight_init, bias_init, gain=1):
    weight_init(module.weight.data, gain=gain)
    bias_init(module.bias.data)
    return module


def init_(m, gain=0.01, activate=False):
    if activate:
        gain = nn.init.calculate_gain('relu')
    return init(m, nn.init.orthogonal_, lambda x: nn.init.constant_(x, 0), gain=gain)


class SelfAttention(nn.Module):
    def __init__(self, n_embd, n_head, max_n_agent, masked=False):
        super(SelfAttention, self).__init__()
        assert n_embd % n_head == 0
        self.masked = masked
        self.n_head = n_head
        self.key = init_(nn.Linear(n_embd, n_embd))
        self.query = init_(nn.Linear(n_embd, n_embd))
        self.value = init_(nn.Linear(n_embd, n_embd))
        self.proj = init_(nn.Linear(n_embd, n_embd))
        self.register_buffer('mask', torch.tril(torch.ones(max_n_agent + 1, max_n_agent + 1))
                             .view(1, 1, max_n_agent + 1, max_n_agent + 1))
        self.att_bp = None

    def forward(self, key, value, query, mask=None):
        B, L, D = query.size()
        k = self.key(key).view(B, L, self.n_head, D // self.n_head).transpose(1, 2)
        q = self.query(query).view(B, L, self.n_head, D // self.n_head).transpose(1, 2)
        v = self.value(value).view(B, L, self.n_head, D // self.n_head).transpose(1, 2)
        att = (q @ k.transpose(-2, -1)) * (1.0 / math.sqrt(k.size(-1)))
        if self.masked and mask is None:
            att = att.masked_fill(self.mask[:, :, :L, :L] == 0, float('-inf'))
        if mask is not None:
            att = att.masked_fill(mask == 0, float('-inf'))
        att = F.softmax(att, dim=-1)
        y = att @ v
        y = y.transpose(1, 2).contiguous().view(B, L, D)
        return self.proj(y)


class LightEncodeBlock(nn.Module):
    def __init__(self, n_embd, n_head, max_n_agent):
        super(LightEncodeBlock, self).__init__()
        self.attn = SelfAttention(n_embd, n_head, max_n_agent, masked=False)

    def forward(self, x, mask=None):
        x = self.attn(x, x, x, mask)
        return x


class TopSkillEncoder(nn.Module):
    def __init__(self, args, max_group_size, device):
        super(TopSkillEncoder, self).__init__()
        self.skill_dim = args.skill_dim
        self.hidden_size = args.hidden_size
        self.n_head = 1
        self.skill_encoder = nn.Sequential(nn.LayerNorm(self.skill_dim),
                                         init_(nn.Linear(self.skill_dim, self.hidden_size), activate=True), nn.GELU())
        self.ln = nn.LayerNorm(self.hidden_size)
        self.blocks = LightEncodeBlock(self.hidden_size, self.n_head, max_group_size)
        self.head = init_(nn.Linear(self.hidden_size, self.skill_dim))
        self.to(device)

    def forward(self, skill, mask):
        skill_embeddings = self.skill_encoder(skill)
        rep = self.blocks.forward(self.ln(skill_embeddings), mask.unsqueeze(1).repeat(1, self.n_head, 1, 1))
        out = self.head(rep)
        out_mask = mask[:, 0:1].float()
        out_mask = out_mask / torch.sum(out_mask, dim=-1, keepdim=True).repeat(1, 1, out_mask.shape[-1])
        masked_out = out_mask @ out
        return masked_out
