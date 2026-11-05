"""Safe, non-executing preflight for upstream VO-MASD shell launcher.

This reads only a shell script as text; it never invokes a shell, installs packages,
loads untrusted checkpoints or contacts the network. It prevents confusing the
ODIS baseline with VO-MASD and prevents unintended eight-million-step runs.
"""
import argparse
import json
import re
from pathlib import Path

VO_MODES = frozenset({'vomasd-3d', 'vomasd-hier', 'vomasd-mixed'})
BENCHMARKS = frozenset({'odis', 'vomasd-single', 'rmappo', 'mappo', 'qmix'})
ASSIGNMENT = re.compile(r'^\s*(algo|map|seed|env|exp)=(?:"([^"]*)"|\'([^\']*)\'|([^\s#]+))\s*(?:#.*)?$', re.MULTILINE)
STEPS = re.compile(r'--num_env_steps\s+(\d+)')
CUDA = re.compile(r'CUDA_VISIBLE_DEVICES=([0-9,]+)')


def inspect_shell_script(source: str, require_vo: bool = True):
    if not isinstance(source, str) or not source or len(source) > 100_000:
        raise ValueError('shell script input invalid')
    entries = {}
    for m in ASSIGNMENT.finditer(source):
        if m.group(1) in entries:
            raise ValueError('duplicate assignment for ' + m.group(1))
        entries[m.group(1)] = next(x for x in m.groups()[1:] if x is not None)
    if 'algo' not in entries:
        raise ValueError('algorithm selection missing')
    alg = entries['algo']
    if alg not in (VO_MODES | BENCHMARKS):
        raise ValueError('unknown training algorithm ' + alg[:50])
    sm = STEPS.findall(source)
    if len(sm) != 1:
        raise ValueError('exactly one training-step bound required')
    steps = int(sm[0])
    if steps <= 0:
        raise ValueError('invalid number of training steps')
    v = {'selected_algorithm':alg,'is_vo_masd':alg in VO_MODES,'num_env_steps':steps,
         'device_pin':CUDA.findall(source),'map':entries.get('map'),
         'seed':entries.get('seed'),'starcraft_environment_required':True,
         'training_executed':False}
    if require_vo and alg not in VO_MODES:
        v['status']='BLOCKED_WRONG_ALGORITHM'
        v['reason']='Upstream launcher selects '+alg+', not VO-MASD; no command executed.'
    elif steps > 100_000:
        v['status']='BLOCKED_RESOURCE_BUDGET'
        v['reason']='Requested steps exceed guarded 100000-step smoke budget; no command executed.'
    else:
        v['status']='READY_FOR_MANUAL_ENVIRONMENT_REVIEW'
        v['reason']='Preflight only; environment and dataset still need independent validation.'
    return v


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('script')
    p.add_argument('--output', required=True)
    args = p.parse_args(argv)
    s = Path(args.script).read_text(encoding='utf-8')
    r = inspect_shell_script(s)
    Path(args.output).write_text(json.dumps(r, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r['status']=='READY_FOR_MANUAL_ENVIRONMENT_REVIEW' else 3

if __name__=='__main__':
    raise SystemExit(main())
