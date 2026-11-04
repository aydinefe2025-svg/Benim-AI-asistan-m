"""Bounded, restartable, offline batch ingestion with durable per-item receipts."""
import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
import feedback_loop

MAX_FILE=2*1024*1024
MAX_ITEMS=10000

def run(input_path, ledger_path, findings_path, limit=1000):
    source=Path(input_path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_FILE:
        raise ValueError('unsafe or oversized input')
    if not isinstance(limit,int) or not 1<=limit<=MAX_ITEMS:
        raise ValueError('invalid limit')
    # Read bytes once. A receipt identifies the precise input line, not a guessed task outcome.
    lines=source.read_bytes().splitlines()
    if len(lines)>MAX_ITEMS:raise ValueError('too many records')
    if any(len(line)>65536 for line in lines):raise ValueError('oversized record')
    ledger=sqlite3.connect(ledger_path,timeout=10)
    try:
        ledger.execute('PRAGMA busy_timeout=10000')
        ledger.execute('CREATE TABLE IF NOT EXISTS receipts (digest TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT NOT NULL)')
        ledger.commit()
        results={'inserted':0,'duplicate':0,'rejected':0,'already_processed':0,'deferred':0}
        findings=feedback_loop.connect(findings_path)
        try:
            for i,line in enumerate(lines):
                if not line.strip():continue
                digest=hashlib.sha256(line).hexdigest()
                if ledger.execute('SELECT 1 FROM receipts WHERE digest=?',(digest,)).fetchone():
                    results['already_processed']+=1;continue
                if sum(results[k] for k in ('inserted','duplicate','rejected'))>=limit:
                    results['deferred']+=1;continue
                try:
                    item=json.loads(line)
                    if not isinstance(item,dict):raise ValueError('record must be object')
                    outcome=feedback_loop.ingest(findings,item)
                    status='inserted' if outcome['inserted'] else 'duplicate'
                    detail=outcome['digest']
                except (ValueError,TypeError,UnicodeDecodeError,json.JSONDecodeError) as exc:
                    status='rejected';detail=str(exc)[:200]
                with ledger:
                    ledger.execute('INSERT OR IGNORE INTO receipts VALUES (?,?,?)',(digest,status,detail))
                results[status]+=1
        finally:
            findings.close()
        results['all_processed']=results['deferred']==0
        return results
    finally:
        ledger.close()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('input');p.add_argument('--ledger',default='batch_receipts.sqlite3')
    p.add_argument('--findings',default='feedback.sqlite3');p.add_argument('--limit',type=int,default=1000)
    a=p.parse_args()
    result=run(a.input,a.ledger,a.findings,a.limit)
    print(json.dumps(result,indent=2))
    if result['rejected'] or result['deferred']:raise SystemExit(2)
if __name__=='__main__':main()