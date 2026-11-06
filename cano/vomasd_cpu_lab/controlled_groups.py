"""Explicit deterministic subgroup fixture, NOT VO-MASD learned Grouper."""
from types import SimpleNamespace
import torch
from native_hierarchy import NativeHierarchyForwardMixin
from original_top_skill_components import TopSkillEncoder
from vomasd_upstream_method import VOMASDHierPolicyOriginalMethod


class FixtureGrouper:
    def __init__(self, partition=((0, 1), (2,))):
        self.partition = tuple(tuple(g) for g in partition)

    def __call__(self, states, btm_z_e, task, test_mode, second_stage=False):
        if task != 'controlled_marl_fixture':
            raise ValueError('fixture only, not a SMAC task')
        b, t, n, d = btm_z_e.shape
        flat = btm_z_e.reshape(-1, n, d)
        if sorted(a for g in self.partition for a in g) != list(range(n)) or not all(self.partition):
            raise ValueError('partition must cover every agent exactly once')
        groups = [{g: row[list(g)] for g in self.partition} for row in flat]
        assignments = torch.empty(b*t,n,1,dtype=torch.long)
        for i,g in enumerate(self.partition):
            assignments[:,list(g),0] = i
        group_logprobs = torch.zeros(b*t,n,1)
        values = torch.zeros(b*t,n,1)
        if second_stage:
            return groups,flat,assignments,group_logprobs,values,{'fixture':True}
        return groups,flat,assignments,group_logprobs,values


class NativeHierarchyHarness(torch.nn.Module, NativeHierarchyForwardMixin):
    def __init__(self, *, skill_dim=4, hidden_size=8, partition=((0,1),(2,)), seed=100):
        torch.nn.Module.__init__(self)
        torch.manual_seed(seed)
        device=torch.device('cpu')
        self.skill_dim=skill_dim
        self.top_skill_num=7
        self.skill_num=9
        self.beta=0.25
        self.tpdv={'dtype':torch.float32,'device':device}
        self.top_codebook=torch.nn.Embedding(self.top_skill_num,skill_dim)
        self.btm_codebook=torch.nn.Embedding(self.skill_num,skill_dim)
        # Follow upstream VOMASDHierPolicy.__init__ narrow uniform initialization.
        self.top_codebook.weight.data.uniform_(-1/self.top_skill_num, 1/self.top_skill_num)
        self.btm_codebook.weight.data.uniform_(-1/self.skill_num, 1/self.skill_num)
        self.top_skill_encoder=TopSkillEncoder(SimpleNamespace(skill_dim=skill_dim,hidden_size=hidden_size),3,device)
        self.grouper=FixtureGrouper(partition)

    forward_codebook=VOMASDHierPolicyOriginalMethod.forward_codebook


def evaluate(seed=42,partition=((0,1),(2,))):
    torch.manual_seed(seed)
    model=NativeHierarchyHarness(partition=partition, seed=seed)
    embeddings=torch.randn(2,3,3,4,requires_grad=True)
    states=torch.randn(2,3,3,2)
    zq,top_diff,btm_diff,group,log_group,v_out,emb_rwd=model.forward_code(states,embeddings,'controlled_marl_fixture',False)
    loss=top_diff.mean()+btm_diff.mean()+zq.square().mean()
    loss.backward()
    maxgrad=max(float(x.grad.abs().max().item()) for x in model.parameters() if x.grad is not None)
    return {'seed':seed,'z_shape':list(zq.shape),'top_loss':round(float(top_diff.mean().item()),8),'bottom_loss':round(float(btm_diff.mean().item()),8),'combined_loss':round(float(loss.item()),8),'grad_norm':round(float(embeddings.grad.norm().item()),8),'param_grad_max':round(maxgrad,8),'finite':bool(torch.isfinite(zq).all() and torch.isfinite(loss)),'second_stage':False,'grouping':'controlled fixture, NOT original MARL Grouper','full_paper_reproduction':False}
