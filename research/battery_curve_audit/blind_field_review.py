#!/usr/bin/env python3
"""Two-stage OFFLINE prospective blinded pair review for battery audits.

The operator retains the predictions in a PRIVATE seal; reviewers receive only
cell-pair aliases and empty verdict fields. The final stage checks form roster,
source receipt and *all original raw time/voltage CSVs* via existing CANO gates.
This does NOT verify true human blinding, site authority, population error rates
or physical data independence. Standard library only. No customer uploads.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import hmac
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile

import customer_preflight as customer
import integrated_customer_gate as integrated
import numeric_equivalence_guard as numeric
import field_pilot_csv_intake as intake
import field_pilot_evidence as field
import field_source_csv_bridge as bridge

SCHEMA = 'cano.battery.blind-review-operator-seal.v1'
PAIRS = ('a','b','flagged')
FORM = ('pair_id','a','b','verdict')
MAX_SEAL_BYTES = 4_000_000
MAX_STRATUM = 2500


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _csv_bytes(header, rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=header, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode('utf-8')


def _new_files(outputs, *, inputs=()):
    """Refuse overwrites; rollback only paths we exclusively created."""
    targets = [Path(p) for p, _ in outputs]
    normalized = [p.resolve(strict=False) for p in targets]
    protected = {Path(p).resolve(strict=False) for p in inputs}
    if len(set(normalized)) != len(normalized) or any(x in protected for x in normalized):
        raise ValueError('REVIEW_REQUIRED: output collides with customer input or another output')
    for p in targets:
        if p.exists() or p.is_symlink():
            raise ValueError('REVIEW_REQUIRED: existing output cannot be overwritten')
        if not p.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output parent directory unavailable')
    created = []
    try:
        for p, content in outputs:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created.append(p)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except Exception:
        for p in created:
            p.unlink(missing_ok=True)
        raise


def _validate_frame_and_roster(cells, pairs, frame, audit):
    if (not isinstance(frame['site_authorization'], dict) or
            frame['site_authorization'].get('permitted') is not True):
        raise ValueError('REVIEW_REQUIRED: site permission attestation required')
    receipt = frame['audit_receipt_sha256']
    if receipt != hashlib.sha256(Path(audit).read_bytes()).hexdigest():
        raise ValueError('REVIEW_REQUIRED: audit report SHA-256 receipt mismatch')
    if len(cells) < 3 or len(cells) > field.MAX_CELLS:
        raise ValueError('REVIEW_REQUIRED: invalid cell roster')
    by_name = {row['cell'] for row in cells}
    if len(by_name) != len(cells):
        raise ValueError('REVIEW_REQUIRED: duplicate cell identifier')
    if {r['partition'] for r in cells} != field.PARTITIONS:
        raise ValueError('REVIEW_REQUIRED: three partitions required')
    if len(pairs) != frame['screened_pair_count']:
        raise ValueError('REVIEW_REQUIRED: declared screened pair frame count mismatch')
    seen = set()
    flagged_count = 0
    for row in pairs:
        a,b = row['a'],row['b']
        if a == b or a not in by_name or b not in by_name:
            raise ValueError('REVIEW_REQUIRED: self/unknown screened pair')
        key = tuple(sorted((a,b)))
        if key in seen:
            raise ValueError('REVIEW_REQUIRED: duplicate screened pair')
        seen.add(key)
        if row['flagged'] not in ('true','false'):
            raise ValueError('REVIEW_REQUIRED: flagged must be exactly true or false')
        flagged_count += row['flagged']=='true'
    if flagged_count != frame['screened_flagged_count']:
        raise ValueError('REVIEW_REQUIRED: flagged pair frame count mismatch')
    if len(pairs) > len(by_name)*(len(by_name)-1)//2:
        raise ValueError('REVIEW_REQUIRED: impossible pair frame size')


def _source_pair_screen(manifest_path, root, audit_path, cells_path):
    """Full rerun: turn exact/near *review candidates* into an operator-only frame.

    Never label an absent match as physically independent. Refuse incomplete
    short/flat coverage and incomparable measurement modes, rather than emit
    false-negative-looking 'clear' pairs.
    """
    manifest_path, audit_path, root = Path(manifest_path),Path(audit_path),Path(root)
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    report=json.loads(audit_path.read_text(encoding='utf-8'))
    if not integrated.verify_report(manifest,root,report):
        raise ValueError('REVIEW_REQUIRED: source audit not reverified')
    if report.get('unscreened_trace_count'):
        raise ValueError('REVIEW_REQUIRED: unscreened short/flat traces cannot be used as clear pairs')
    if report.get('split') is None:
        raise ValueError('REVIEW_REQUIRED: no source-candidate cell split')
    numeric_report=numeric.build_numeric_audit(manifest,root)
    cells=intake.read_csv(cells_path,intake.CELLS,field.MAX_CELLS)
    aliases=sorted(r['cell'] for r in cells)
    if len(set(aliases))!=len(aliases):
        raise ValueError('REVIEW_REQUIRED: duplicate cell roster')
    original_cells={r['cell'] for r in numeric_report['all_curve_identity']}
    if set(aliases)!=original_cells:
        raise ValueError('REVIEW_REQUIRED: field roster not equal to measured source cells')
    expected={r['cell']:r['partition'] for r in report['split']['assignments']}
    if any(expected.get(r['cell'])!=r['partition'] for r in cells):
        raise ValueError('REVIEW_REQUIRED: cell partition differs from raw-source audit')
    modes={c:set() for c in aliases}
    for row in numeric_report['all_curve_identity']:
        modes[row['cell']].add(row['mode'])
    flagged=set()
    for group in numeric_report['duplicate_groups']:
        by_cell=sorted({r['cell'] for r in group})
        for i,a in enumerate(by_cell):
            for b in by_cell[i+1:]:
                flagged.add((a,b))
    for record in report.get('near_candidates',[]):
        a,b=sorted((record['a']['cell'],record['b']['cell']))
        if a!=b:
            flagged.add((a,b))
    rows=[]
    for i,a in enumerate(aliases):
        for b in aliases[i+1:]:
            if not (modes[a] & modes[b]):
                raise ValueError('REVIEW_REQUIRED: no comparable mode between source cell pair')
            rows.append({'a':a,'b':b,'flagged':'true' if (a,b) in flagged else 'false'})
    if not rows or len(rows)>field.MAX_REVIEWS:
        raise ValueError('REVIEW_REQUIRED: pair screen exceeds prospective pilot compute budget')
    return rows


def generate_screen(manifest_path, root, audit_path, cells_path, pairs_out, frame_out):
    """Derive pair candidate flags exclusively from reverified source measurements."""
    rows=_source_pair_screen(manifest_path,root,audit_path,cells_path)
    frame={'schema':intake.SCHEMA,
           'site_authorization':{'permitted':False,'reference':'REPLACE_WITH_SITE_AUTHORIZATION'},
           'audit_receipt_sha256':_sha(audit_path),
           'screened_pair_count':len(rows),
           'screened_flagged_count':sum(r['flagged']=='true' for r in rows)}
    files=[manifest_path,audit_path,cells_path]
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    files.extend(customer.safe_path(Path(root),entry['path']) for entry in manifest['files'])
    _new_files([(pairs_out,_csv_bytes(PAIRS,rows)),
                (frame_out,(json.dumps(frame,sort_keys=True,ensure_ascii=False,indent=2)+'\n').encode())],
               inputs=files)
    return {'screened_pair_count':len(rows),
            'screened_flagged_count':frame['screened_flagged_count'],
            'site_authorization_independently_verified':False,
            'field_acceptance':'NOT_ESTABLISHED'}


def prepare(cells_path, pairs_path, frame_path, audit_path,
            reviewer_a_form, reviewer_b_form, seal_path, *, per_stratum=50, secret=None):
    """Create private sealed predictions and two independent, prediction-free forms."""
    inputs = (cells_path, pairs_path, frame_path, audit_path)
    if type(per_stratum) is not int or not 1 <= per_stratum <= MAX_STRATUM:
        raise ValueError('REVIEW_REQUIRED: invalid per-stratum sample budget')
    if secret is None:
        secret = secrets.token_bytes(32)
    if type(secret) is not bytes or len(secret) != 32:
        raise ValueError('REVIEW_REQUIRED: sampler requires 32 private random bytes')
    cells = intake.read_csv(cells_path,intake.CELLS,field.MAX_CELLS)
    pairs = intake.read_csv(pairs_path,PAIRS,field.MAX_REVIEWS)
    frame = intake.read_frame(frame_path)
    _validate_frame_and_roster(cells,pairs,frame,audit_path)
    groups = {True: [], False: []}
    for row in pairs:
        a,b = sorted((row['a'],row['b']))
        flagged = row['flagged']=='true'
        token = (a+'\0'+b).encode('utf-8')
        pair_id=hmac.new(secret,b'pair-id\0'+token,hashlib.sha256).hexdigest()[:32]
        priority=hmac.new(secret,b'rank\0'+token,hashlib.sha256).digest()
        groups[flagged].append((priority, {'pair_id':pair_id,'a':a,'b':b,'flagged':flagged}))
    samples = []
    for flagged in (True,False):
        samples.extend(row for _,row in sorted(groups[flagged],key=lambda z:z[0])[:per_stratum])
    samples.sort(key=lambda r:r['pair_id'])
    def form(tag):
        rank = lambda r:hmac.new(secret,tag+r['pair_id'].encode(),hashlib.sha256).digest()
        rows = sorted(samples,key=rank)
        return _csv_bytes(FORM,[{'pair_id':r['pair_id'],'a':r['a'],'b':r['b'],'verdict':''}
                                for r in rows])
    seal = {'schema':SCHEMA,
            'input_sha256': {key:_sha(path) for key,path in zip(
                ('cells','pairs','frame','audit'),inputs)},
            'sampled':samples,
            'screened_pair_count':len(pairs),
            'screened_flagged_count':sum(row['flagged']=='true' for row in pairs),
            'selected_flagged':sum(row['flagged'] for row in samples),
            'selected_clear':sum(not row['flagged'] for row in samples),
            'selection_design':'stratified_without_replacement; signed labels are not shown to reviewers',
            'limitations':['Sampling frame and site authorization are operator asserted, not independently verified.',
                           'The two reviewer forms hide the model decision, but true human blinding is not technically proven.',
                           'Pair-level observations may share cells; they are not independent physical trials.',
                           'Selection does not establish field FPR/FNR or a certifiable acceptance.']}
    payload = (json.dumps(seal,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    _new_files([(reviewer_a_form,form(b'reviewer-A:')),
                (reviewer_b_form,form(b'reviewer-B:')),
                (seal_path,payload)],inputs=inputs)
    return {'selected_flagged':seal['selected_flagged'],
            'selected_clear':seal['selected_clear'],
            'field_acceptance':'NOT_ESTABLISHED',
            'operator_predictions_are_private':True}


def finalize(manifest_path, root, audit_path, cells_path, pairs_path, frame_path,
             reviewer_a_form, reviewer_b_form, seal_path, summary_path, *,
             reviewer_a_id, reviewer_b_id, private_ledger_path=None):
    """Reconcile both forms with private pair predictions then use original binder."""
    inputs=(manifest_path,audit_path,cells_path,pairs_path,frame_path,
            reviewer_a_form,reviewer_b_form,seal_path)
    for field_id in (reviewer_a_id,reviewer_b_id):
        if not isinstance(field_id,str) or not field_id.strip() or len(field_id)>100:
            raise ValueError('REVIEW_REQUIRED: invalid reviewer identifier')
    if reviewer_a_id==reviewer_b_id:
        raise ValueError('REVIEW_REQUIRED: distinct reviewer identities required')
    if Path(seal_path).stat().st_size>MAX_SEAL_BYTES:
        raise ValueError('REVIEW_REQUIRED: oversized operator seal')
    seal=json.loads(Path(seal_path).read_text(encoding='utf-8'))
    if not isinstance(seal,dict) or seal.get('schema')!=SCHEMA:
        raise ValueError('REVIEW_REQUIRED: invalid operator seal')
    for key,path in zip(('cells','pairs','frame','audit'),(cells_path,pairs_path,frame_path,audit_path)):
        if seal.get('input_sha256',{}).get(key)!=_sha(path):
            raise ValueError('REVIEW_REQUIRED: operator pair/source inputs changed or hash mismatch')
    if not isinstance(seal.get('input_sha256'), dict):
        raise ValueError('REVIEW_REQUIRED: invalid operator input hashes')
    screened = intake.read_csv(pairs_path,PAIRS,field.MAX_REVIEWS)
    original_pairs = {}
    for item in screened:
        if item['flagged'] not in ('true','false'):
            raise ValueError('REVIEW_REQUIRED: invalid source-screen prediction')
        key = tuple(sorted((item['a'],item['b'])))
        if key in original_pairs:
            raise ValueError('REVIEW_REQUIRED: duplicate source-screen pair')
        original_pairs[key] = item['flagged']=='true'
    actual_screen = _source_pair_screen(manifest_path,root,audit_path,cells_path)
    provided = intake.read_csv(pairs_path,PAIRS,field.MAX_REVIEWS)
    if sorted(provided,key=lambda r:(r['a'],r['b'])) != actual_screen:
        raise ValueError('REVIEW_REQUIRED: operator predictions differ from source-recomputed screen')
    sampled = seal.get('sampled')
    if not isinstance(sampled,list) or not sampled or len(sampled)>2*MAX_STRATUM:
        raise ValueError('REVIEW_REQUIRED: missing operator sampled pairs')
    keys = {}
    for row in sampled:
        if (not isinstance(row,dict) or set(row)!={'pair_id','a','b','flagged'} or
                type(row['flagged']) is not bool or not isinstance(row['pair_id'],str) or
                len(row['pair_id'])!=32 or not all(c in '0123456789abcdef' for c in row['pair_id'])):
            raise ValueError('REVIEW_REQUIRED: malformed operator sampling seal')
        if (tuple(sorted((row['a'],row['b']))) not in original_pairs or
                row['flagged'] != original_pairs[tuple(sorted((row['a'],row['b'])))]):
            raise ValueError('REVIEW_REQUIRED: operator seal prediction differs from screened pair frame')
        if row['pair_id'] in keys:
            raise ValueError('REVIEW_REQUIRED: duplicate operator pair identifier')
        keys[row['pair_id']] = row
    if (sum(row['flagged'] for row in sampled)!=seal.get('selected_flagged') or
            sum(not row['flagged'] for row in sampled)!=seal.get('selected_clear')):
        raise ValueError('REVIEW_REQUIRED: operator selection counters inconsistent')
    reviewer_map=[]
    for form_path in (reviewer_a_form,reviewer_b_form):
        rows=intake.read_csv(form_path,FORM,field.MAX_REVIEWS)
        if len(rows)!=len(keys):
            raise ValueError('REVIEW_REQUIRED: incomplete technician form roster')
        answers = {}
        for row in rows:
            pair_id=row['pair_id']
            if (pair_id not in keys or pair_id in answers or
                    row['a']!=keys[pair_id]['a'] or row['b']!=keys[pair_id]['b']):
                raise ValueError('REVIEW_REQUIRED: technician form pair identifier/roster mismatch')
            if row['verdict'] not in field.VERDICTS:
                raise ValueError('REVIEW_REQUIRED: missing or invalid technician verdict')
            answers[pair_id]=row['verdict']
        reviewer_map.append(answers)
    with tempfile.TemporaryDirectory(prefix='cano-blind-review-') as tempdir:
        safe_temp=Path(tempdir)/'combined_private_reviews.csv'
        combined=[{'a':r['a'],'b':r['b'],'flagged':'true' if r['flagged'] else 'false',
                   'reviewer_a_id':reviewer_a_id,'reviewer_a_verdict':reviewer_map[0][r['pair_id']],
                   'reviewer_b_id':reviewer_b_id,'reviewer_b_verdict':reviewer_map[1][r['pair_id']]}
                  for r in sampled]
        safe_temp.write_bytes(_csv_bytes(intake.REVIEWS,combined))
        if os.name=='posix':safe_temp.chmod(0o600)
        manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
        if not isinstance(manifest,dict) or not isinstance(manifest.get('files'),list):
            raise ValueError('REVIEW_REQUIRED: malformed source manifest')
        root=Path(root)
        protected=list(inputs)
        for entry in manifest['files']:
            if not isinstance(entry,dict) or not isinstance(entry.get('path'),str):
                raise ValueError('REVIEW_REQUIRED: malformed source mapping')
            protected.append(customer.safe_path(root,entry['path']))
        targets=[Path(summary_path)] + ([Path(private_ledger_path)] if private_ledger_path is not None else [])
        if (len({p.resolve(strict=False) for p in targets})!=len(targets) or
                {p.resolve(strict=False) for p in protected}.intersection(
                    {p.resolve(strict=False) for p in targets})):
            raise ValueError('REVIEW_REQUIRED: output collides with protected customer input')
        return bridge.run_bound(manifest_path,root,audit_path,cells_path,
                                 safe_temp,frame_path,summary_path,private_ledger_path)


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    sub=ap.add_subparsers(dest='command',required=True)
    screen=sub.add_parser('screen',help='Build private pair flags directly from independently reaudited raw CSVs')
    for name in ('manifest','audit_report','cells','pairs_out','frame_out'):
        screen.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    screen.add_argument('--root',type=Path)
    p=sub.add_parser('prepare',help='Make two prediction-blind forms and private sealed operator register')
    for name in ('cells','pairs','frame','audit_report','reviewer_a_form','reviewer_b_form','operator_seal'):
        p.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    p.add_argument('--per-stratum',type=int,default=50)
    f=sub.add_parser('finalize',help='Combine independent reviewer forms and reverify original source data')
    for name in ('manifest','audit_report','cells','pairs','frame','reviewer_a_form',
                 'reviewer_b_form','operator_seal','summary'):
        f.add_argument('--'+name.replace('_','-'),type=Path,required=True)
    f.add_argument('--root',type=Path)
    f.add_argument('--reviewer-a-id',type=str,required=True)
    f.add_argument('--reviewer-b-id',type=str,required=True)
    f.add_argument('--private-ledger',type=Path)
    opts=ap.parse_args(argv)
    try:
        if opts.command=='screen':
            root=opts.root if opts.root is not None else opts.manifest.resolve().parent
            r=generate_screen(opts.manifest,root,opts.audit_report,opts.cells,
                              opts.pairs_out,opts.frame_out)
            print('SOURCE_SCREEN_REVIEW_ONLY: candidate pairs=',r['screened_flagged_count'],
                  'of',r['screened_pair_count'],'no field certificate; site permission FALSE until verified by operator')
            return 0
        if opts.command=='prepare':
            r=prepare(opts.cells,opts.pairs,opts.frame,opts.audit_report,
                      opts.reviewer_a_form,opts.reviewer_b_form,opts.operator_seal,
                      per_stratum=opts.per_stratum)
            print('PREPARED: review forms omit algorithm flags; selected flagged=',
                  r['selected_flagged'],'clear=',r['selected_clear'],'; NOT_ESTABLISHED')
            return 0
        root=opts.root if opts.root is not None else opts.manifest.resolve().parent
        result=finalize(opts.manifest,root,opts.audit_report,opts.cells,
                        opts.pairs,opts.frame,opts.reviewer_a_form,opts.reviewer_b_form,
                        opts.operator_seal,opts.summary,
                        reviewer_a_id=opts.reviewer_a_id,reviewer_b_id=opts.reviewer_b_id,
                        private_ledger_path=opts.private_ledger)
        print(result['decision']+': source rechecked; site acceptance NOT_ESTABLISHED')
        return 0 if result['decision']=='PILOT_ONLY_NOT_CERTIFIED' else 2
    except (OSError, ValueError, RuntimeError, TypeError, KeyError, UnicodeError,
            json.JSONDecodeError, csv.Error) as exc:
        print('REVIEW_REQUIRED: '+str(exc),file=sys.stderr)
        return 2


if __name__=='__main__':
    sys.exit(main())
