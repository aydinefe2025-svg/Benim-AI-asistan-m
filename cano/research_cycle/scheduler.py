"""Bounded local tick scheduler: no background process or network calls."""
from contextlib import closing
import argparse, json, sqlite3, time
from pathlib import Path
import core
import resilience
ROOT=Path(__file__).resolve().parent
DB=ROOT/'scheduler.sqlite3'
TASKS=('sift_synthetic','sift_robustness')
INTERVAL=3600

def connect(path=DB):
    c=sqlite3.connect(path,timeout=5)
    c.execute('PRAGMA busy_timeout=5000')
    c.execute('CREATE TABLE IF NOT EXISTS ticks (name TEXT PRIMARY KEY, last_attempt INTEGER NOT NULL, last_status TEXT NOT NULL)')
    c.commit()
    return c

def tick(c, now=None, runner=None):
    now=int(time.time()) if now is None else int(now)
    if now<0:raise ValueError('invalid time')
    def local_repair(name):
        with closing(core.connect()) as task_db:
            result=resilience.repair(task_db,name)
        return result['state']=='verified'
    runner=runner or local_repair
    results=[]
    for name in TASKS:
        # BEGIN IMMEDIATE serializes competing ticks; never start an overlapping run.
        c.execute('BEGIN IMMEDIATE')
        try:
            row=c.execute('SELECT last_attempt FROM ticks WHERE name=?',(name,)).fetchone()
            if row and now-row[0]<INTERVAL:
                c.rollback();results.append({'name':name,'status':'cooldown'});continue
            c.execute('INSERT INTO ticks VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET last_attempt=excluded.last_attempt,last_status=excluded.last_status',(name,now,'claimed'))
            c.commit()
        except BaseException:
            c.rollback();raise
        try:
            outcome=runner(name)
            status='completed' if outcome is True else 'failed'
        except Exception as e:
            status='failed';outcome=type(e).__name__
        with c:c.execute('UPDATE ticks SET last_status=? WHERE name=?',(status,name))
        results.append({'name':name,'status':status,'detail':str(outcome)[:120]})
    return {'results':results,'all_completed':all(x['status']=='completed' for x in results)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('tick','status'));a=p.parse_args()
    with closing(connect()) as c:
        if a.command=='status':result={'ticks':[{'name':n,'last_attempt':t,'status':s} for n,t,s in c.execute('SELECT name,last_attempt,last_status FROM ticks ORDER BY name')]}
        else:result=tick(c)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if a.command=='tick' and not result['all_completed']:raise SystemExit(1)
if __name__=='__main__':main()