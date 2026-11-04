"""Read-only integration health ledger; no credentials or network writes."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone

SERVICES = ('notion', 'github')
STATES = ('verified', 'blocked', 'unverified')

def validate(record):
    if not isinstance(record, dict) or set(record) != {'service','status','checked_at','detail'}:
        raise ValueError('invalid record schema')
    if record['service'] not in SERVICES or record['status'] not in STATES:
        raise ValueError('unknown service/status')
    if not isinstance(record['detail'], str) or not 1 <= len(record['detail']) <= 400:
        raise ValueError('invalid detail')
    if not isinstance(record['checked_at'], str):
        raise ValueError('invalid timestamp')
    dt = datetime.fromisoformat(record['checked_at'].replace('Z','+00:00'))
    if dt.tzinfo is None:
        raise ValueError('timestamp requires timezone')
    return record

def summary(records):
    latest = {}
    for item in records:
        validate(item)
        key=item['service']
        if key not in latest or item['checked_at'] > latest[key]['checked_at']:
            latest[key] = item
    return {'ready': all(latest.get(s,{}).get('status') == 'verified' for s in SERVICES),
            'services': {s: latest.get(s, {'service':s,'status':'unverified','detail':'No check recorded'}) for s in SERVICES}}

def append(path, record):
    validate(record)
    p=Path(path)
    if p.is_symlink():
        raise ValueError('symlink ledger forbidden')
    if p.exists() and p.stat().st_size > 1_000_000:
        raise ValueError('ledger too large')
    rows=[] if not p.exists() else json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(rows,list) or len(rows)>1000:
        raise ValueError('invalid ledger')
    summary(rows)
    rows.append(record)
    tmp=p.with_suffix(p.suffix+'.tmp')
    if tmp.is_symlink():
        raise ValueError('unsafe temporary path')
    try:
        tmp.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(p)
    finally:
        tmp.unlink(missing_ok=True)
    return summary(rows)

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('ledger')
    ap.add_argument('--service',choices=SERVICES)
    ap.add_argument('--status',choices=STATES)
    ap.add_argument('--detail')
    a=ap.parse_args()
    if a.service:
        if not a.status or not a.detail: ap.error('status and detail required')
        record={'service':a.service,'status':a.status,'detail':a.detail,'checked_at':datetime.now(timezone.utc).isoformat()}
        result=append(a.ledger,record)
    else:
        p=Path(a.ledger)
        result=summary(json.loads(p.read_text(encoding='utf-8')) if p.exists() else [])
    print(json.dumps(result,ensure_ascii=False,indent=2))