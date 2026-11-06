"""Bounded CPU hierarchy wiring+group sensitivity, NOT VO-MASD full paper reproduction."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import torch
from controlled_groups import evaluate
from group_sensitivity import run
from native_parity import METHOD_SHA256, verify_method_provenance


def experiment():
    verify_method_provenance()
    seeds=[evaluate(seed) for seed in range(16)]
    sensitivity=run(range(32))
    return {'protocol':'CANO_VOMASD_HIERARCHY_CONTROLLED_2026-11-06_V1',
            'paper_doi':'10.24963/ijcai.2025/538',
            'upstream_repo':'https://github.com/LucasCJYSDL/VOMASD',
            'upstream_blob_hier_policy':'621980122d13f1c8dab31c4ccabe9f5c4099c95f',
            'upstream_blob_vomasd_module':'f94834f63dded1b34b8b566d6449004c0fb2982c',
            'upstream_blob_transformer':'8e0e4222597a6fa0f2295144066a811f99588e15',
            'upstream_codebook_method_sha256':METHOD_SHA256,
            'torch_version':torch.__version__,
            'synthetic_only':True,
            'learned_grouper_executed':False,
            'starcraft_smac_executed':False,
            'paper_win_rates_replicated':False,
            'full_model_executed':False,
            'source_scope':'adapted forward_code, source-equivalent TopSkillEncoder + SelfAttention, exact upstream forward_codebook, deterministic fixture Grouper',
            'seeded_gradients':seeds,
            'group_sensitivity':sensitivity}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    args=p.parse_args(argv)
    target=Path(args.output)
    if target.is_symlink() or not target.parent.is_dir():
        raise ValueError('unsafe output path')
    data=experiment()
    payload=(json.dumps(data,indent=2,sort_keys=True,ensure_ascii=False)+'\n').encode('utf-8')
    # tmp uniquely allocated; fsync before atomic replacement and cleanup on failure.
    fd,name=tempfile.mkstemp(prefix='.hier-',suffix='.tmp',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(name,target)
    finally:
        Path(name).unlink(missing_ok=True)
    digest=hashlib.sha256(payload).hexdigest()
    print(json.dumps({'ok':True,'output':str(target),'sha256':digest,'seeds':len(data['seeded_gradients']),
                      'group_cases':data['group_sensitivity']['cases'],'full_paper_reproduction':False}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
