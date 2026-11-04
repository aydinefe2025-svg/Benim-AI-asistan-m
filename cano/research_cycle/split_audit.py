"""Offline scene-level split leakage audit for user-supplied metadata; no data downloaded."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

FIELDS = {'pair_id','scene_id','split','image_a_sha256','image_b_sha256'}
SPLITS = {'train','val','test'}
MAX_ROWS = 100000

def audit(rows):
    rows = list(rows)
    if not rows or len(rows) > MAX_ROWS:
        raise ValueError('row count outside accepted range')
    ids, scenes, images = set(), {}, {}
    counts = {s: 0 for s in sorted(SPLITS)}
    problems = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != FIELDS:
            raise ValueError(f'row {index}: unexpected columns')
        pid, scene, split = (row[k] for k in ('pair_id','scene_id','split'))
        if any(not isinstance(x,str) or not x.strip() or len(x)>256 for x in (pid,scene,split)) or split not in SPLITS:
            raise ValueError(f'row {index}: invalid identifiers or split')
        if pid in ids:
            problems.append({'kind':'duplicate_pair_id','pair_id':pid})
        ids.add(pid)
        counts[split] += 1
        scenes.setdefault(scene, set()).add(split)
        hashes = [row['image_a_sha256'],row['image_b_sha256']]
        for digest in hashes:
            if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError(f'row {index}: invalid SHA-256')
            images.setdefault(digest, set()).add(split)
    # Aggregate every affected split, rather than reporting only the first pair.
    for scene, affected in scenes.items():
        if len(affected) > 1:
            problems.append({'kind':'scene_leakage','scene_id':scene,'splits':sorted(affected)})
    for digest, affected in images.items():
        if len(affected) > 1:
            problems.append({'kind':'image_leakage','sha256':digest,'splits':sorted(affected)})
    # Deduplicate repeated leakage reports.
    unique = {json.dumps(p,sort_keys=True):p for p in problems}
    problems = [unique[k] for k in sorted(unique)]
    return {'ok':not problems and sum(v>0 for v in counts.values())>=2,
            'pair_count':len(rows),'scene_count':len(scenes),'split_counts':counts,
            'issues':problems + ([{'kind':'insufficient_splits'}] if sum(v>0 for v in counts.values())<2 else [])}

def load_csv(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError('invalid or oversized CSV')
    with path.open('r',encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None or len(reader.fieldnames)!=len(FIELDS) or set(reader.fieldnames)!=FIELDS:
            raise ValueError('invalid CSV header')
        rows=[]
        for row in reader:
            if len(rows)>=MAX_ROWS: raise ValueError('too many rows')
            rows.append(row)
    return audit(rows)

if __name__ == '__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('metadata_csv'); args=ap.parse_args()
    try:
        result=load_csv(args.metadata_csv)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        raise SystemExit(0 if result['ok'] else 2)
    except (ValueError,OSError,UnicodeError,csv.Error) as e:
        print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False))
        raise SystemExit(2)