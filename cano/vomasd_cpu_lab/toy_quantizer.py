"""CPU smoke of the SOURCE-FAITHFUL isolated VO-MASD Hier VQ codebook.

All arrays are synthetic and seeded. This is NOT a reproduction of IJCAI-25
training, StarCraft evaluation, dynamic grouping or downstream policy reward.
"""
import argparse
import hashlib
import json
from pathlib import Path
import torch
from upstream_vomasd_quantizer import IsolatedVOMASDHierCodebook


def experiment(steps=120, seed=20261105):
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    means = torch.tensor([[-3.,-3.,0.,0.],[-3.,3.,0.,0.],[3.,-3.,0.,0.],[3.,3.,0.,0.]])
    # Independently sampled train/test observations, labels not used for learning.
    train = means.repeat_interleave(80, dim=0) + .4 * torch.randn(320,4)
    test = means.repeat_interleave(30, dim=0) + .4 * torch.randn(120,4)
    # Initialize codebook far from centers so improvement can be measured.
    initial = means + torch.tensor([[1.2,-1.0,1.,.5],[.8,.9,-1.,.9],[-1.2,.8,.5,-1.],[1.,-1.1,-.5,.7]])
    q = IsolatedVOMASDHierCodebook(initial, torch.randn(8,4))
    with torch.no_grad():
        start=float(((q.forward_codebook(test,True)-test)**2).mean())
    optimizer=torch.optim.Adam(q.top_codebook.parameters(), lr=.09)
    for _ in range(steps):
        optimizer.zero_grad(set_to_none=True)
        quantized=q.forward_codebook(train,True)
        loss=((quantized-train)**2).mean()
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        final=float(((q.forward_codebook(test,True)-test)**2).mean())
        d=torch.cdist(test, q.top_codebook.weight).square()
        used=int(torch.unique(d.argmin(dim=1)).numel())
        weight_hash=hashlib.sha256(q.top_codebook.weight.detach().numpy().tobytes()).hexdigest()
    return {'source_component':'VOMASDHierPolicy.forward_codebook (transcribed, isolated)',
            'synthetic_data':True,'paper_result_replicated':False,'starcraft_run':False,
            'train_samples':len(train),'heldout_samples':len(test),'latent_dim':4,
            'distinct_codes_used_on_holdout':used,'steps':steps,'seed':seed,
            'heldout_mse_start':round(start,6),'heldout_mse_end':round(final,6),
            'improvement_percent':round((1-final/start)*100,3),
            'codebook_weights_sha256':weight_hash,
            'torch_version':torch.__version__}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    a=p.parse_args()
    results=experiment()
    target=Path(a.output)
    target.write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(results,ensure_ascii=False))

if __name__=='__main__':main()
