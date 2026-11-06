"""VO-MASD Hier original forward_code with isolated grouping environment.

Original source LucasCJYSDL/VOMASD pinned blob 621980122d13f1c8dab31c4ccabe9f5c4099c95f
MIT (c) 2024 Jiayu Chen. We copied the original method's operations without
modifying the algorithm; only its owning class and dependencies are reduced.
Note: grouping and encoder are controlled substitutes, NOT original SMAC grouper.
"""
import torch


def check(x):
    return torch.as_tensor(x)


class NativeHierarchyForwardMixin:
    def forward_code(self, states, btm_z_e, task, test_mode, second_stage=False):
        # torch.Size([32, 25, 3, 117]) torch.Size([32, 25, 3, 5])
        states = check(states).to(**self.tpdv)
        btm_z_e = check(btm_z_e).to(**self.tpdv)
        bs, seq_len, n_agent = states.shape[0], states.shape[1], states.shape[2]

        if second_stage:
            grouping_rlt, btm_z_e, group, log_group, v_out, _ = self.grouper(states, btm_z_e, task, test_mode=test_mode, second_stage=second_stage)
        else:
            grouping_rlt, btm_z_e, group, log_group, v_out = self.grouper(states, btm_z_e, task, test_mode=test_mode)

        btm_skills, btm_masks = [], []
        for g in grouping_rlt:
            for sg in g:
                sg_skills = g[sg].reshape(-1, self.skill_dim)
                sg_size = sg_skills.shape[0]
                padding_skills = torch.zeros(size=(n_agent, self.skill_dim), device=sg_skills.device, dtype=sg_skills.dtype)
                padding_skills[:sg_size] = padding_skills[:sg_size] + sg_skills
                padding_masks = torch.zeros(size=(n_agent, n_agent), device=sg_skills.device, dtype=torch.int)
                padding_masks[:, :sg_size] = 1
                btm_skills.append(padding_skills)
                btm_masks.append(padding_masks)
        btm_skills = torch.stack(btm_skills, dim=0)
        btm_masks = torch.stack(btm_masks, dim=0)
        pre_top_skills = self.top_skill_encoder(btm_skills, btm_masks)

        top_skill_ls = []
        b_id = 0
        for g in grouping_rlt:
            top_skill_dict = {}
            for sg in g:
                for agent_id in list(sg):
                    top_skill_dict[agent_id] = pre_top_skills[b_id]
                b_id += 1
            top_skill = []
            for i in range(n_agent):
                top_skill.append(top_skill_dict[i])
            top_skill_ls.append(torch.cat(top_skill, dim=0))
        top_skills = torch.stack(top_skill_ls, dim=0)
        top_z_e = top_skills
        top_z_q = self.forward_codebook(top_z_e, is_top=True)
        top_diff = torch.mean((top_z_q.detach() - top_z_e) ** 2, dim=-1, keepdim=True) +\
                   self.beta * torch.mean((top_z_q - top_z_e.detach()) ** 2, dim=-1, keepdim=True)
        top_z_q = top_z_e + (top_z_q - top_z_e).detach()

        btm_z_q = self.forward_codebook(btm_z_e, is_top=False)
        btm_diff = torch.mean((btm_z_q.detach() - btm_z_e) ** 2, dim=-1, keepdim=True) +\
                   self.beta * torch.mean((btm_z_q - btm_z_e.detach()) ** 2, dim=-1, keepdim=True)
        btm_z_q = btm_z_e + (btm_z_q - btm_z_e).detach()

        emb_rwd = - (torch.mean((btm_z_q.detach() - btm_z_e) ** 2, dim=-1, keepdim=True) +\
                     torch.mean((top_z_q.detach() - top_z_e) ** 2, dim=-1, keepdim=True)).detach().clone()

        top_z_q = top_z_q.reshape(bs, seq_len, n_agent, self.skill_dim)
        btm_z_q = btm_z_q.reshape(bs, seq_len, n_agent, self.skill_dim)
        z_q = torch.cat([top_z_q, btm_z_q], dim=-1)

        if second_stage:
            return z_q
        return z_q, top_diff, btm_diff, group, log_group, v_out, emb_rwd
