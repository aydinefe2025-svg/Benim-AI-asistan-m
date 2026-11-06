"""Small controlled experiment assessing hierarchy response to group composition.
No learned grouper, no SC2: *not* a published VO-MASD result.
"""
import json
import torch
from controlled_groups import NativeHierarchyHarness

PARTITIONS=(((0,1),(2,)),((0,1,2),),((0,),(1,),(2,)),((0,2),(1,)))


def run(seeds=range(32)):
    rows=[]
    torch.set_num_threads(1)
    for seed in seeds:
        torch.manual_seed(seed)
        model=NativeHierarchyHarness(seed=seed)
        embeddings=torch.randn(2,3,3,4)
        states=torch.randn(2,3,3,2)
        reference=None
        outs=[]
        top_latents=[]
        hook=model.top_skill_encoder.register_forward_hook(lambda mod,ins,out:top_latents.append(out.detach().clone()))
        try:
            with torch.no_grad():
                for part in PARTITIONS:
                    model.grouper.partition=part
                    zq, top, btm,group,log,val,reward = model.forward_code(states,embeddings,'controlled_marl_fixture',True)
                    outs.append(zq.clone())
        finally:
            hook.remove()
        ref=outs[0]
        diffs=[float((x-ref).abs().max()) for x in outs[1:]]
        # TopSkillEncoder gives group-level output; different numbers of groups =>
        # compare same 2-group partition of differently composed agents only.
        # first partition groups agent0+1, agent2; fourth has agent0+2, agent1.
        group_latent_diff=float((top_latents[0]-top_latents[-1]).abs().max())
        # count distinct top codes via exact values per agent (quantizer is discrete)
        distinct=len(torch.unique(ref[...,:4].reshape(-1,4),dim=0))
        rows.append({'seed':seed,'max_output_change_vs_three_alternative_partitions':max(diffs),'max_group_encoder_latent_change':group_latent_diff,'distinct_quantized_top_codes':distinct})
    return {'scope':'source-adapted forward_code plus genuine-shaped TopSkillEncoder; grouper is controlled fixture',
            'upstream_learner_executed':False,'sc2_executed':False,'paper_results_replicated':False,
            'seeds':len(rows),'partitions_per_seed':len(PARTITIONS),'cases':len(rows)*len(PARTITIONS),
            'fraction_seeds_with_output_change':sum(x['max_output_change_vs_three_alternative_partitions']>0 for x in rows)/len(rows),
            'median_top_code_utilization':float(torch.tensor([x['distinct_quantized_top_codes'] for x in rows],dtype=torch.float32).median()),
            'max_encoder_latent_change':max(x['max_group_encoder_latent_change'] for x in rows),
            'rows':rows}


if __name__=='__main__':
    print(json.dumps(run(),indent=2))
