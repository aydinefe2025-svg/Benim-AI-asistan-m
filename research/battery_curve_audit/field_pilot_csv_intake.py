#!/usr/bin/env python3
"""Offline CSV -> existing two-reviewer field-pilot assessor, with redacted output.

This intake does NOT prove the site permission/receipt claims. Raw data are never
uploaded. Review CSV, cells CSV and frame JSON are private local metadata. An
optional private ledger is explicitly requested, never created by default.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import sys

import field_pilot_evidence as gate

SCHEMA = 'cano.battery.field-intake-frame.v1'
CELLS = ('cell','device','batch','campaign','partition')
REVIEWS = ('a','b','flagged','reviewer_a_id','reviewer_a_verdict',
           'reviewer_b_id','reviewer_b_verdict')
MAX_CSV_BYTES = 1_000_000
MAX_FRAME_BYTES = 64_000


def read_csv(path, columns, max_rows):
    """Strict header and record width; no guessed defaults for missing columns."""
    raw = Path(path).read_bytes()
    if not raw or len(raw) > MAX_CSV_BYTES or b'\x00' in raw:
        raise ValueError('REVIEW_REQUIRED: CSV empty, unsafe, or too large')
    try:
        stream=io.StringIO(raw.decode('utf-8-sig'),newline='')
        reader=csv.reader(stream, strict=True)
        header=next(reader)
        if tuple(header)!=columns:
            raise ValueError('REVIEW_REQUIRED: unknown, reordered, or duplicate CSV header')
        records=[]
        for i,row in enumerate(reader,2):
            if len(row)!=len(columns) or any(not x or len(x)>100 or '\n' in x or '\r' in x for x in row):
                raise ValueError(f'REVIEW_REQUIRED: invalid CSV record at row {i}')
            records.append(dict(zip(columns,row)))
            if len(records)>max_rows:
                raise ValueError('REVIEW_REQUIRED: too many CSV records')
    except (StopIteration, UnicodeError, csv.Error) as exc:
        raise ValueError('REVIEW_REQUIRED: malformed CSV encoding or rows') from exc
    return records


def read_frame(path):
    data=Path(path).read_bytes()
    if not data or len(data)>MAX_FRAME_BYTES:
        raise ValueError('REVIEW_REQUIRED: invalid frame size')
    frame=json.loads(data.decode('utf-8-sig'))
    if (not isinstance(frame,dict) or set(frame)!={'schema','site_authorization',
            'audit_receipt_sha256','screened_pair_count','screened_flagged_count'} or
            frame['schema']!=SCHEMA):
        raise ValueError('REVIEW_REQUIRED: unknown frame schema or keys')
    return frame


def evaluate(cells_csv, reviews_csv, frame_json):
    frame=read_frame(frame_json)
    cells=read_csv(cells_csv,CELLS,gate.MAX_CELLS)
    reviews=read_csv(reviews_csv,REVIEWS,gate.MAX_REVIEWS)
    ledger={
        'schema':gate.SCHEMA,
        'site_authorization':frame['site_authorization'],
        'audit_receipt_sha256':frame['audit_receipt_sha256'],
        'screened_pair_count':frame['screened_pair_count'],
        'screened_flagged_count':frame['screened_flagged_count'],
        'cells':[], 'assignments':[], 'reviews':[],
    }
    for row in cells:
        ledger['cells'].append({k:row[k] for k in ('cell','device','batch','campaign')})
        ledger['assignments'].append({'cell':row['cell'],'partition':row['partition']})
    for row in reviews:
        if row['flagged'] not in ('true','false'):
            raise ValueError('REVIEW_REQUIRED: flagged must be exactly true or false')
        ledger['reviews'].append({
            'a':row['a'],'b':row['b'],'flagged':row['flagged']=='true',
            'reviewer_a':{'id':row['reviewer_a_id'],'verdict':row['reviewer_a_verdict']},
            'reviewer_b':{'id':row['reviewer_b_id'],'verdict':row['reviewer_b_verdict']},
        })
    # Single source of truth: use the existing audited field assessor.
    result=gate.assess(ledger)
    return result,ledger


def save(result, output_path, *, private=None,private_path=None,inputs=()):
    """Preflight all outputs; create only new files, rollback newly created files."""
    outputs=[(Path(output_path),result)]
    if private is not None or private_path is not None:
        if private is None or private_path is None:
            raise ValueError('REVIEW_REQUIRED: private ledger requires explicit opt-in')
        outputs.append((Path(private_path),private))
    target_paths=[p.resolve(strict=False) for p,_ in outputs]
    input_paths={Path(p).resolve(strict=False) for p in inputs}
    if len(target_paths)!=len(set(target_paths)) or input_paths.intersection(target_paths):
        raise ValueError('REVIEW_REQUIRED: output collides with customer input or another output')
    for p,_ in outputs:
        if p.exists() or p.is_symlink():
            raise ValueError('REVIEW_REQUIRED: existing output cannot be overwritten')
        if not p.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output parent directory does not exist')
    created=[]
    try:
        for p,data in outputs:
            raw=(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+'\n').encode('utf-8')
            fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            created.append(p)
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        for p in created:
            p.unlink(missing_ok=True)
        raise


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--cells',required=True,type=Path)
    ap.add_argument('--reviews',required=True,type=Path)
    ap.add_argument('--frame',required=True,type=Path)
    ap.add_argument('--summary',required=True,type=Path)
    ap.add_argument('--private-ledger',type=Path,help='explicit opt-in: customer identifiers and reviewer IDs')
    args=ap.parse_args(argv)
    try:
        result,ledger=evaluate(args.cells,args.reviews,args.frame)
        save(result,args.summary,private=ledger if args.private_ledger else None,
             private_path=args.private_ledger,inputs=(args.cells,args.reviews,args.frame))
        print(f"{result['decision']}: reviewed={result['reviewed_pair_count']}; "
              f"consensus={result['consensus_reviewed']}; field acceptance NOT_ESTABLISHED")
        return 2 if result['decision'].startswith('BLOCK_') else 0
    except (ValueError,KeyError,TypeError,OSError,UnicodeError,json.JSONDecodeError) as exc:
        print('REVIEW_REQUIRED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
