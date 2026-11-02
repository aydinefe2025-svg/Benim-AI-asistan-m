"""Classify scientific assertions, never a reproducer's exit code alone."""
import json
import re
from pathlib import Path
root=Path(__file__).resolve().parent
logs=root/'results'
summary=[]
for issue in (5532,5521):
    states=[]
    for phase in ('baseline','fixed'):
        rows=json.loads((logs/f'{phase}_mmcif.json').read_text())
        rows=[r for r in rows if r['issue']==issue]
        states.append('PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL')
    summary.append(dict(issue=issue,baseline=states[0],retest=states[1]))
for issue,name in ((5515,'neighbor'),(5493,'checkpoint'),(5494,'cpupme')):
    states=[]
    for suffix in ('','_retest'):
        text=(logs/f'{name}{suffix}.log').read_text()
        if issue==5515:
            arrays=re.findall(r': (\[[0-9, ]+\])',text)
            states.append('SKIP' if len(arrays)!=6 else 'FAIL' if any(any(json.loads(a)) for a in arrays) else 'PASS')
        elif issue==5493:
            counts=re.findall(r'forces differ after loading at (\d+) of 20 checkpoints',text)
            dx=re.findall(r'max\|dx\| ([0-9.e+-]+) nm',text)
            states.append('SKIP' if len(counts)!=2 or len(dx)!=2 else 'FAIL' if any(int(c) for c in counts) or any(float(x) for x in dx) else 'PASS')
        else:
            # Bitwise equality is diagnostic; compiler errors corroborate silent fallback.
            if 'errors generated' in text and 'forces are bitwise equal to GPU PME' in text:
                states.append('FAIL')
            else:
                states.append('SKIP') # Distinct forces alone do not prove the CPU kernel ran.
    summary.append(dict(issue=issue,baseline=states[0],retest=states[1]))
result=dict(tests=summary,cuda='SKIP: platform absent in installed Windows wheel',
            scope='Local OpenMM 8.6.1 mmCIF fixes only; C++ CPU/GPU defects remain unresolved')
(logs/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
raise SystemExit(any(r['retest']=='FAIL' for r in summary))
