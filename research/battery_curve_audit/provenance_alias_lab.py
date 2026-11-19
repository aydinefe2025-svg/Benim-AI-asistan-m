#!/usr/bin/env python3
"""Deterministic adversarial field provenance-alias stress lab (SYNTHETIC ONLY).

Source aliases are fictional. A review flag is not proof of a physical link,
reviewer independence, or a real laboratory error rate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random

import field_pilot_evidence as gate

SCHEMA = 'cano.battery.provenance-alias-lab.v1'
FIELDS = ('device', 'batch', 'campaign')

def fullwidth(text):
    return ''.join(chr(ord(c)+0xFEE0) if '!' <= c <= '~' else c for c in text)

def variant(text, kind):
    return {
        'lowercase': lambda x: x.lower(),
        'outer_ascii_whitespace': lambda x: '  '+x+'  ',
        'fullwidth_unicode_nfkc': fullwidth,
        'outer_unicode_whitespace': lambda x: '\u3000'+x+'\u3000',
        'lowercase_fullwidth': lambda x: fullwidth(x.lower()),
        'mixed_unicode_padding': lambda x: '  '+fullwidth(x.lower())+'\u3000',
    }[kind](text)

VARIANTS = ('lowercase', 'outer_ascii_whitespace', 'fullwidth_unicode_nfkc',
            'outer_unicode_whitespace', 'lowercase_fullwidth', 'mixed_unicode_padding')
CONTROL_VARIANTS = ('different_hyphen_count', 'different_delimiter')


def fixture(base, field, spelling):
    # The only partially matching metadata field is the selected field.
    cells=[]
    for name in 'ABCD':
        row={'cell': name,'device':'DEVICE-'+name+'-'+base,
             'batch':'BATCH-'+name+'-'+base,'campaign':'CAMPAIGN-'+name+'-'+base}
        cells.append(row)
    cells[0][field] = base
    cells[1][field] = spelling
    return {
        'schema': gate.SCHEMA,
        'site_authorization':{'permitted':True,'reference':'SYNTHETIC-NOT-SIGNED'},
        'audit_receipt_sha256':'0'*64,
        'cells':cells,
        'assignments':[{'cell':n,'partition':p} for n,p in
                       zip('ABCD',('train','validation','test','train'))],
        'screened_pair_count':6,'screened_flagged_count':0,
        'reviews':[{'a':'A','b':'B','flagged':False,
                    'reviewer_a':{'id':'T1','verdict':'independent'},
                    'reviewer_b':{'id':'T2','verdict':'independent'}}]
    }


def run_all(trials=50, seed=20261119):
    if type(trials) is not int or not 1 <= trials <= 1000:
        raise ValueError('REVIEW_REQUIRED: trials outside [1,1000]')
    if type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise ValueError('REVIEW_REQUIRED: seed outside uint32')
    rng=random.Random(seed)
    seen=Counter()
    for field in FIELDS:
        for kind in VARIANTS:
            for _ in range(trials):
                label='SERIAL-'+''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(8))
                result=gate.assess(fixture(label, field, variant(label, kind)))
                seen['synthetic_alias_cases']+=1
                if result['decision']=='BLOCK_PROVENANCE_LEAKAGE':
                    seen['conservative_alias_reviews']+=1
                elif result['decision']=='PILOT_METRICS_ONLY':
                    seen['alias_escaping_split_review']+=1
                else:
                    raise AssertionError('Unexpected provenance decision '+result['decision'])
    # Negative controls intentionally change characters not equivalent under
    # Unicode NFKC + casefold + outer-whitespace trim. These are not physical labels.
    for kind in CONTROL_VARIANTS:
        for _ in range(3*trials):
            label='SERIAL-'+''.join(rng.choice('ABCDEFGHJKLMNPQRSTUVWXYZ0123456789') for _ in range(8))
            change=label.replace('-', '--') if kind=='different_hyphen_count' else label.replace('-', '_')
            result=gate.assess(fixture(label, 'device', change))
            seen['synthetic_distinct_controls']+=1
            if result['decision']=='PILOT_METRICS_ONLY':
                seen['controls_not_blocked']+=1
            elif result['decision']=='BLOCK_PROVENANCE_LEAKAGE':
                seen['distinct_controls_reviewed']+=1
            else:
                raise AssertionError('Unexpected distinct-control decision '+result['decision'])
    out={'schema':SCHEMA,'trials_per_alias_variant_per_field':trials,
         'seed':seed,'scenario_count':seen['synthetic_alias_cases']+seen['synthetic_distinct_controls'],
         'synthetic_alias_cases':seen['synthetic_alias_cases'],
         'conservative_alias_reviews':seen['conservative_alias_reviews'],
         'alias_escaping_split_review':seen['alias_escaping_split_review'],
         'synthetic_distinct_controls':seen['synthetic_distinct_controls'],
         'controls_not_blocked':seen['controls_not_blocked'],
         'distinct_controls_reviewed':seen['distinct_controls_reviewed'],
         'fields_checked':list(FIELDS),'alias_transformations':list(VARIANTS),
         'result':'SYNTHETIC_PROVENANCE_REVIEW_ONLY',
         'real_instrument_identity_verified':False,
         'real_field_false_positive_or_negative_rate_established':False,
         'notes':['The alias transformations are only NFKC/casefold/outer whitespace; arbitrary serial typos are not resolved.',
                  'Equal normalized strings are possible related source metadata, not proof of same instrument or experiment.',
                  'Distinct synthetic control strings do not establish physical independence.']}
    return out


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--trials',type=int,default=50)
    ap.add_argument('--seed',type=int,default=20261119)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args(argv)
    report=run_all(args.trials,args.seed)
    if report['alias_escaping_split_review'] or report['distinct_controls_reviewed']:
        raise RuntimeError('Unexpected alias guard regression; no report accepted')
    b=(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+'\n').encode('utf-8')
    if not args.output.parent.is_dir():
        raise ValueError('Output directory must exist')
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(b);f.flush();os.fsync(f.fileno())
    print(f"PROVENANCE SIMULATION PASS: {report['scenario_count']} scenarios; "
          f"{report['conservative_alias_reviews']} alias reviews; "
          f"{report['controls_not_blocked']} distinct controls")
    return 0

if __name__=='__main__':
    raise SystemExit(main())
