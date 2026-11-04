"""Bounded offline experiment runner. A completed task is not scientific validation."""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'tasks.sqlite3'
ALLOWED = {'sift_synthetic': 'amalga_sift_pilot.py', 'sift_robustness': 'amalga_robustness_suite.py'}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def connect(path=DB):
    c = sqlite3.connect(path, timeout=20)
    c.execute('PRAGMA busy_timeout=20000')
    c.execute('CREATE TABLE IF NOT EXISTS tasks (name TEXT PRIMARY KEY, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, output TEXT, updated TEXT NOT NULL, run_id TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY, task_name TEXT, run_id TEXT, status TEXT, note TEXT, time TEXT)')
    c.commit()
    return c

def add(c, name):
    if name not in ALLOWED:
        raise ValueError('Task not allowlisted')
    c.execute('INSERT OR IGNORE INTO tasks(name,status,updated) VALUES(?,?,?)', (name,'pending',now()))
    c.commit()

def claim(c, name):
    add(c,name)
    rid=uuid.uuid4().hex
    c.execute('BEGIN IMMEDIATE')
    row=c.execute('SELECT status FROM tasks WHERE name=?',(name,)).fetchone()
    if row[0]=='running':
        c.rollback()
        raise RuntimeError('Task already running; use recover after inspecting a crashed worker')
    c.execute('UPDATE tasks SET status=?,attempts=attempts+1,updated=?,run_id=? WHERE name=?',('running',now(),rid,name))
    c.execute('INSERT INTO events(task_name,run_id,status,note,time) VALUES(?,?,?,?,?)',(name,rid,'running','claimed',now()))
    c.commit()
    return rid

def verify(name, stdout):
    """Validate experiment evidence rather than trusting process exit status alone."""
    try:
        if name=='sift_synthetic':
            x=json.loads(stdout)
            assert x['mode']=='synthetic' and isinstance(x['ratio_matches'],int) and isinstance(x['ransac_inliers'],int)
            assert x['ratio_matches']>=4 and 4 <= x['ransac_inliers'] <= x['ratio_matches']
            assert math.isfinite(x['median_ground_truth_error_px']) and 0 <= x['median_ground_truth_error_px'] < 100
        elif name=='sift_robustness':
            x=json.loads(stdout)
            assert x['runs']==12 and x['blank_image_test']=='passed'
            assert all(math.isfinite(x[k]) for k in ('inlier_fraction_min','inlier_fraction_median','median_ground_truth_error_px_max','median_ground_truth_error_px_median'))
            assert 0 <= x['inlier_fraction_min'] <= x['inlier_fraction_median'] <= 1
            assert 0 <= x['median_ground_truth_error_px_median'] <= x['median_ground_truth_error_px_max'] < 100
        else:
            return False
        return True
    except (ValueError,KeyError,TypeError,AssertionError,OverflowError):
        return False

def run(c,name,timeout=120):
    if name not in ALLOWED: raise ValueError('Task not allowlisted')
    if not 1 <= timeout <= 1800: raise ValueError('timeout out of bounds')
    rid=claim(c,name)
    try:
        p=subprocess.run([sys.executable,str(ROOT/ALLOWED[name])],cwd=ROOT,capture_output=True,text=True,timeout=timeout,check=False)
        output=p.stdout[-16000:]
        error=p.stderr[-4000:]
        status='completed' if p.returncode==0 and verify(name,output) else 'failed'
        note=json.dumps({'exit_code':p.returncode,'stdout':output,'stderr':error},ensure_ascii=False)
    except (subprocess.TimeoutExpired,OSError) as e:
        status='failed';note=f'{type(e).__name__}: {e}'
    with c:
        changed=c.execute('UPDATE tasks SET status=?,output=?,updated=? WHERE name=? AND run_id=? AND status=?',(status,note[-20000:],now(),name,rid,'running')).rowcount
        if changed != 1: raise RuntimeError('Task ownership changed unexpectedly')
        c.execute('INSERT INTO events(task_name,run_id,status,note,time) VALUES(?,?,?,?,?)',(name,rid,status,note[-1500:],now()))
    return {'name':name,'status':status,'run_id':rid,'detail':note[-1000:]}

def recover(c,name):
    """Manual crash recovery only; never silently restart potentially active work."""
    if name not in ALLOWED:raise ValueError('Task not allowlisted')
    with c:
        changed=c.execute("UPDATE tasks SET status='interrupted',updated=? WHERE name=? AND status='running'",(now(),name)).rowcount
        if changed:c.execute('INSERT INTO events(task_name,status,note,time) VALUES(?,?,?,?)',(name,'interrupted','manual recovery; previous worker must be stopped',now()))
    return {'name':name,'recovered':bool(changed)}

def health(c):
    import importlib.util
    scripts={name:{'exists':(ROOT / path).is_file(),'sha256':hashlib.sha256((ROOT/path).read_bytes()).hexdigest() if (ROOT/path).is_file() else None} for name,path in ALLOWED.items()}
    return {'healthy':all(x['exists'] for x in scripts.values()) and importlib.util.find_spec('cv2') is not None and importlib.util.find_spec('numpy') is not None and c.execute('PRAGMA integrity_check').fetchone()[0]=='ok', 'scripts':scripts,'database_integrity':c.execute('PRAGMA integrity_check').fetchone()[0], 'dependencies':{'cv2':importlib.util.find_spec('cv2') is not None,'numpy':importlib.util.find_spec('numpy') is not None},'running_tasks':c.execute("SELECT COUNT(*) FROM tasks WHERE status='running'").fetchone()[0]}

def report(c):
    rows=c.execute('SELECT name,status,attempts,updated FROM tasks ORDER BY name').fetchall()
    return {'tasks':[dict(zip(('name','status','attempts','updated'),r)) for r in rows], 'counts':dict(c.execute('SELECT status,COUNT(*) FROM tasks GROUP BY status')),'allowed_tasks':sorted(ALLOWED)}

def evidence_audit(c):
    """Check stored completion claims against JSON evidence, without running tasks."""
    rows = c.execute("SELECT name,status,output FROM tasks ORDER BY name").fetchall()
    items=[]
    for name,status,output in rows:
        valid = None
        reason = 'not_completed'
        if status == 'completed':
            try:
                record=json.loads(output)
                valid = record.get('exit_code') == 0 and verify(name,record.get('stdout',''))
                reason = 'evidence_valid' if valid else 'evidence_invalid'
            except (ValueError,TypeError,AttributeError):
                valid=False;reason='malformed_record'
        items.append({'task':name,'status':status,'valid':valid,'reason':reason})
    return {'passed':bool(items) and all(i['valid'] is True for i in items),'items':items}

def file_manifest(root=ROOT):
    """Generate a manifest of only allowlisted scripts, without following symlinks."""
    result=[]
    for name,relative in sorted(ALLOWED.items()):
        path=root/relative
        if path.is_symlink() or not path.is_file():
            result.append({'task':name,'file':relative,'error':'missing_or_symlink'})
        else:
            data=path.read_bytes()
            result.append({'task':name,'file':relative,'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    return {'schema':1,'files':result}

def verify_manifest(manifest,root=ROOT):
    if manifest.get('schema')!=1 or not isinstance(manifest.get('files'),list):return False
    expected=file_manifest(root)
    return expected == manifest and all('error' not in x for x in expected['files'])

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','run','status','recover','health','audit','manifest','verify-manifest'])
    p.add_argument('--task',choices=sorted(ALLOWED))
    p.add_argument('--timeout',type=int,default=120)
    p.add_argument('--manifest-path',type=Path,default=ROOT/'trusted_script_manifest.json')
    a=p.parse_args()
    c=connect()
    try:
            if a.command=='init':
                for name in ALLOWED:add(c,name)
                result=report(c)
            elif a.command=='health':
                result=health(c)
            elif a.command=='audit':
                result=evidence_audit(c)
            elif a.command=='manifest':
                result=file_manifest()
            elif a.command=='verify-manifest':
                try:
                    manifest=json.loads(a.manifest_path.read_text(encoding='utf-8'))
                    valid=verify_manifest(manifest)
                    result={'passed':valid,'manifest_path':str(a.manifest_path),'reason':'match' if valid else 'mismatch'}
                except (OSError,ValueError,TypeError,AttributeError) as exc:
                    result={'passed':False,'reason':type(exc).__name__}
            elif a.command in ('run','recover'):
                if not a.task:p.error('--task required')
                result=run(c,a.task,a.timeout) if a.command=='run' else recover(c,a.task)
            else:result=report(c)
    finally:
        c.close()
    print(json.dumps(result,indent=2,ensure_ascii=False))
    if a.command=='run' and result['status']!='completed':sys.exit(1)
    if a.command=='health' and not result['healthy']:sys.exit(1)
    if a.command in ('audit','verify-manifest') and not result['passed']:sys.exit(1)
if __name__=='__main__':main()