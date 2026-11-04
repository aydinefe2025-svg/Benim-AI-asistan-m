"""Atomic findings + receipts in one SQLite database; offline and bounded."""
import argparse
import hashlib
import json
import sqlite3
import time
from pathlib import Path
import feedback_loop

MAX_BYTES=2*1024*1024
MAX_LINES=10000

def run(source, database, limit=1000, fault_after_finding=False):
    source=Path(source)
    if source.is_symlink() or not source.is_file() or source.stat().st_size>MAX_BYTES:
        raise ValueError('unsafe input')
    if not isinstance(limit,int) or not 1<=limit<=MAX_LINES:raise ValueError('invalid limit')
    lines=source.read_bytes().splitlines()
    if len(lines)>MAX_LINES or any(len(x)>65536 for x in lines):raise ValueError('input limits exceeded')
    db=Path(database)
    if db.is_symlink():raise ValueError('symlink database forbidden')
    conn=feedback_loop.connect(db)
    result={'inserted':0,'duplicate':0,'rejected':0,'already_processed':0,'deferred':0}
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS receipts (digest TEXT PRIMARY KEY, status TEXT NOT NULL, detail TEXT NOT NULL)')
        conn.commit()
        for line in lines:
            if not line.strip():continue
            digest=hashlib.sha256(line).hexdigest()
            if conn.execute('SELECT 1 FROM receipts WHERE digest=?',(digest,)).fetchone():
                result['already_processed']+=1;continue
            if sum(result[k] for k in ('inserted','duplicate','rejected'))>=limit:
                result['deferred']+=1;continue
            try:
                item=json.loads(line)
                normalized=feedback_loop.validate(item)
                canonical=json.dumps(normalized,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                finding_hash=hashlib.sha256(canonical.encode()).hexdigest()
                with conn:
                    cursor=conn.execute('INSERT OR IGNORE INTO findings VALUES(?,?,?,?,?,?,?)',(finding_hash,normalized['kind'],normalized['title'],normalized['source'],normalized['evidence'],'pending_review',int(time.time())))
                    if fault_after_finding:raise RuntimeError('injected crash')
                    status='inserted' if cursor.rowcount else 'duplicate'
                    conn.execute('INSERT INTO receipts VALUES (?,?,?)',(digest,status,finding_hash))
            except (ValueError,TypeError,UnicodeDecodeError,json.JSONDecodeError) as exc:
                with conn:
                    conn.execute('INSERT INTO receipts VALUES (?,?,?)',(digest,'rejected',str(exc)[:200]))
                status='rejected'
            result[status]+=1
        result['all_processed']=result['deferred']==0
        return result
    finally:
        conn.close()

def audit(database):
    db=Path(database)
    if not db.is_file() or db.is_symlink():return {'ok':False,'checked':0,'errors':['missing or unsafe database']}
    conn=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True)
    try:
        errors=[];n=0
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok':errors.append('database integrity')
        for status,detail in conn.execute('SELECT status,detail FROM receipts'):
            n+=1
            if status not in ('inserted','duplicate','rejected'):errors.append('invalid receipt')
            if status in ('inserted','duplicate'):
                row=conn.execute('SELECT kind,title,source,evidence FROM findings WHERE digest=?',(detail,)).fetchone()
                if row is None:
                    errors.append('orphan receipt')
                else:
                    canonical=json.dumps(dict(zip(('kind','title','source','evidence'),row)),ensure_ascii=False,sort_keys=True,separators=(',',':'))
                    if hashlib.sha256(canonical.encode()).hexdigest()!=detail:
                        errors.append('tampered finding content')
        if not n:errors.append('empty receipts')
        return {'ok':not errors,'checked':n,'errors':errors}
    except sqlite3.DatabaseError as exc:
        return {'ok':False,'checked':0,'errors':[str(exc)[:120]]}
    finally:conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('input');p.add_argument('--db',default='atomic_findings.sqlite3');p.add_argument('--limit',type=int,default=1000);a=p.parse_args()
    r=run(a.input,a.db,a.limit);print(json.dumps(r));raise SystemExit(2 if r['rejected'] or r['deferred'] else 0)