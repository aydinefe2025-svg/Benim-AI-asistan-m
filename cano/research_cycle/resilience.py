"""Fail-closed, bounded recovery for allowlisted local experiments."""
from contextlib import closing
import json
import sqlite3
import time
from pathlib import Path
import core

TRANSIENT = ('TimeoutExpired', 'database is locked')

def diagnose(c):
    status=core.report(c)
    audit=core.evidence_audit(c)
    manifest_path=core.ROOT/'trusted_script_manifest.json'
    try:
        manifest_ok=core.verify_manifest(json.loads(manifest_path.read_text(encoding='utf-8')))
    except (OSError, ValueError, TypeError, AttributeError):
        manifest_ok=False
    health=core.health(c)
    issues=[]
    if not manifest_ok: issues.append('script_manifest_mismatch')
    if not health['healthy']: issues.append('health_failed')
    if health['running_tasks']: issues.append('running_tasks_need_manual_review')
    if not audit['passed']: issues.append('incomplete_or_invalid_evidence')
    return {'ready':not issues,'issues':issues,'health':health,'audit':audit,'status':status,'manifest_ok':manifest_ok}

def repair(c,task,max_attempts=2,delay=0):
    """Never auto-recover running work, change files, or ignore manifest mismatch."""
    if task not in core.ALLOWED: raise ValueError('not allowlisted')
    if not 1 <= max_attempts <= 3: raise ValueError('attempt limit must be 1..3')
    if not 0 <= delay <= 5: raise ValueError('delay must be 0..5 seconds')
    check=diagnose(c)
    if not check['manifest_ok'] or not check['health']['healthy']:
        return {'task':task,'state':'blocked','reason':'environment_or_manifest_invalid','attempts':0}
    row=c.execute('SELECT status FROM tasks WHERE name=?',(task,)).fetchone()
    if row and row[0]=='running':
        return {'task':task,'state':'blocked','reason':'running_task_requires_manual_review','attempts':0}
    results=[]
    for i in range(max_attempts):
        result=core.run(c,task,timeout=120)
        results.append({'status':result['status'],'run_id':result['run_id']})
        if result['status']=='completed':
            return {'task':task,'state':'verified','attempts':i+1,'runs':results}
        if not any(k in result['detail'] for k in TRANSIENT):
            return {'task':task,'state':'failed','reason':'non_transient_failure','attempts':i+1,'runs':results}
        if i+1 < max_attempts:time.sleep(delay)
    return {'task':task,'state':'failed','reason':'retry_budget_exhausted','attempts':len(results),'runs':results}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['diagnose','repair'])
    p.add_argument('--task',choices=sorted(core.ALLOWED))
    a=p.parse_args()
    with closing(core.connect()) as c:
        result=diagnose(c) if a.command=='diagnose' else repair(c,a.task)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if (a.command=='diagnose' and not result['ready']) or (a.command=='repair' and result['state']!='verified'):
        raise SystemExit(1)