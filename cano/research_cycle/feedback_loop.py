"""Bounded, offline evidence-driven feedback loop. No network or autonomous code execution."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import time

ROOT=Path(__file__).resolve().parent
DB=ROOT/'feedback.sqlite3'
VALID_KINDS={'observation','hypothesis','experiment_result','issue'}
MAX_BYTES=64*1024

def connect(path=DB):
    c=sqlite3.connect(path)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute('CREATE TABLE IF NOT EXISTS findings (digest TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, source TEXT NOT NULL, evidence TEXT NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS review_events (id INTEGER PRIMARY KEY AUTOINCREMENT,digest TEXT NOT NULL, decision TEXT NOT NULL, reason TEXT NOT NULL,created INTEGER NOT NULL)')
    c.commit()
    return c

def validate(item):
    if not isinstance(item,dict) or set(item)!={'kind','title','source','evidence'}:raise ValueError('required fields: kind,title,source,evidence')
    if item['kind'] not in VALID_KINDS:raise ValueError('invalid kind')
    for k in ('title','source','evidence'):
        if not isinstance(item[k],str) or not item[k].strip() or len(item[k])>4000:raise ValueError('invalid '+k)
    if len(item['title'])>160:raise ValueError('title too long')
    return {k:item[k].strip() for k in ('kind','title','source','evidence')}

def ingest(c,item):
    x=validate(item)
    canonical=json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256(canonical.encode()).hexdigest()
    with c:
        cur=c.execute('INSERT OR IGNORE INTO findings VALUES(?,?,?,?,?,?,?)',(digest,x['kind'],x['title'],x['source'],x['evidence'],'pending_review',int(time.time())))
    return {'digest':digest,'inserted':bool(cur.rowcount),'status':'pending_review'}

def review(c,digest,decision,reason):
    if decision not in ('accepted','rejected'):raise ValueError('invalid decision')
    if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:raise ValueError('reason required')
    with c:
        row=c.execute('SELECT status FROM findings WHERE digest=?',(digest,)).fetchone()
        if not row:raise ValueError('unknown digest')
        if row[0]!='pending_review':raise ValueError('already reviewed')
        c.execute('UPDATE findings SET status=? WHERE digest=?',(decision,digest))
        c.execute('INSERT INTO review_events(digest,decision,reason,created) VALUES(?,?,?,?)',(digest,decision,reason.strip(),int(time.time())))
    return {'digest':digest,'status':decision}

def report(c):
    counts=dict(c.execute('SELECT status,COUNT(*) FROM findings GROUP BY status'))
    pending=[{'digest':r[0],'kind':r[1],'title':r[2],'source':r[3]} for r in c.execute("SELECT digest,kind,title,source FROM findings WHERE status='pending_review' ORDER BY created,digest LIMIT 100")]
    return {'counts':counts,'pending':pending,'reviewed':sum(v for k,v in counts.items() if k!='pending_review')}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('ingest','status','review'))
    p.add_argument('--file',type=Path)
    p.add_argument('--digest')
    p.add_argument('--decision',choices=('accepted','rejected'))
    p.add_argument('--reason')
    a=p.parse_args()
    c=connect()
    try:
            if a.command=='ingest':
                if not a.file or a.file.is_symlink() or not a.file.is_file() or a.file.stat().st_size>MAX_BYTES:p.error('safe input file required (<=64KiB)')
                result=ingest(c,json.loads(a.file.read_text(encoding='utf-8')))
            elif a.command=='review':
                if not all((a.digest,a.decision,a.reason)):p.error('digest, decision and reason required')
                result=review(c,a.digest,a.decision,a.reason)
            else:result=report(c)
    finally:
        c.close()
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()