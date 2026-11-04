"""Fail-closed cross-check between batch receipts and durable findings."""
import argparse
import json
import sqlite3
from pathlib import Path


def audit(ledger_path, findings_path):
    ledger_path, findings_path = Path(ledger_path), Path(findings_path)
    if not ledger_path.is_file() or not findings_path.is_file():
        return {'ok': False, 'errors': ['missing database'], 'checked': 0}
    errors=[]
    checked=0
    ledger=sqlite3.connect(f'file:{ledger_path.resolve()}?mode=ro', uri=True)
    findings=sqlite3.connect(f'file:{findings_path.resolve()}?mode=ro', uri=True)
    try:
        for label,conn in [('ledger',ledger),('findings',findings)]:
            if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                errors.append(label+' database integrity failure')
        for status,detail in ledger.execute('SELECT status,detail FROM receipts'):
            checked+=1
            if status not in ('inserted','duplicate','rejected'):
                errors.append('invalid receipt status')
            if status in ('inserted','duplicate'):
                row=findings.execute('SELECT status FROM findings WHERE digest=?',(detail,)).fetchone()
                if not row: errors.append('receipt references missing finding: '+detail[:16])
                elif row[0] not in ('pending_review','accepted','rejected'):
                    errors.append('invalid finding review state')
        return {'ok': not errors and checked>0, 'checked':checked, 'errors':errors or (['no receipts'] if checked==0 else [])}
    except sqlite3.DatabaseError as exc:
        return {'ok':False,'checked':checked,'errors':['database error: '+str(exc)[:120]]}
    finally:
        ledger.close();findings.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ledger');p.add_argument('findings');a=p.parse_args()
    result=audit(a.ledger,a.findings)
    print(json.dumps(result,indent=2))
    if not result['ok']:raise SystemExit(2)