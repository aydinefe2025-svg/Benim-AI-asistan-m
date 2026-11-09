"""Non-regression gate for GitHub Actions dependencies, without extra packages.

Keeps a dated, reviewed *count* baseline for legacy tag/branch action references;
new workflows must use immutable action SHAs. This is deliberately NOT a YAML
parser, upstream action trust assessment or a GitHub lockfile generator. Run the
official gh actions-lock CLI for transitive SHA pinning and a full security check.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SHA40 = re.compile(r"^[0-9a-fA-F]{40}$")
USES = re.compile(r"^\s*(?:-\s*)?uses\s*:\s*(.*?)\s*$")
# A common unsafe CI trigger. This guard is conservative and requires review
# if it occurs; it cannot verify privileges, trusted actors or remote includes.
PULL_REQUEST_TARGET = re.compile(r"^\s*pull_request_target\s*:")
INLINE_TARGET = re.compile(r"^\s*on\s*:\s*\[[^]]*\bpull_request_target\b")


def _check_baseline(baseline: dict) -> dict[str, int]:
    if not isinstance(baseline, dict) or baseline.get('schema') != 1:
        raise ValueError('Unexpected baseline schema')
    counts = baseline.get('max_movable_per_workflow')
    if not isinstance(counts, dict) or not counts:
        raise ValueError('Expected non-empty workflow baseline')
    for name, maximum in counts.items():
        if not (isinstance(name, str) and name.endswith(('.yml', '.yaml'))
                and '/' not in name and '\\' not in name and name not in ('.yml', '.yaml')
                and type(maximum) is int and maximum >= 0):
            raise ValueError('Unsafe or invalid baseline entry')
    return counts


def _classify(ref: str) -> str:
    if not ref or '${{' in ref:
        return 'unknown'
    if ref.startswith('./'):
        return 'local'
    if ref.startswith('docker://'):
        return 'unknown'  # mutable container tags are not exempt
    if '@' not in ref:
        return 'unknown'
    source, version = ref.rsplit('@', 1)
    if not source or not version or any(ch.isspace() for ch in source+version):
        return 'unknown'
    if source.startswith(('.', '/')):
        return 'unknown'
    return 'pinned' if SHA40.fullmatch(version) else 'mutable'


def evaluate_policy(workflows_dir: Path, baseline: dict) -> dict:
    """Audit all tracked GitHub Action references; refuse security regressions."""
    limits = _check_baseline(baseline)
    folder = Path(workflows_dir)
    if not folder.is_dir():
        raise FileNotFoundError(str(folder))
    paths = sorted([*folder.glob('*.yml'), *folder.glob('*.yaml')])
    if not paths:
        raise ValueError('No workflow files available for security audit')
    violations: list[str] = []
    mutable_total = pinned_total = unknown_total = local_total = 0
    per_file = []
    for path in paths:
        if path.is_symlink():
            violations.append(f'{path.name}: symlinked workflow requires review')
            continue
        content = path.read_text(encoding='utf-8')
        mutable = pinned = unknown = local = 0
        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.lstrip()
            if not stripped or stripped.startswith('#'):
                continue
            if PULL_REQUEST_TARGET.match(line) or INLINE_TARGET.match(line):
                violations.append(f'{path.name}:{line_no}: pull_request_target requires manual security review')
            match = USES.match(line)
            if not match:
                continue
            raw = match.group(1).split('#', 1)[0].strip()
            reference = raw[1:-1] if len(raw)>=2 and raw[:1] == raw[-1:] and raw[0] in "'\"" else raw
            kind = _classify(reference)
            if kind == 'mutable':
                mutable += 1
            elif kind == 'pinned':
                pinned += 1
            elif kind == 'local':
                local += 1
            else:
                unknown += 1
                violations.append(f'{path.name}:{line_no}: unrecognized `uses:` requires manual review')
        maximum = limits.get(path.name, 0)  # unknown workflow gets no mutable reference exemption
        if mutable > maximum:
            violations.append(f'{path.name}: {mutable} mutable refs exceed reviewed baseline {maximum}')
        mutable_total += mutable
        pinned_total += pinned
        unknown_total += unknown
        local_total += local
        per_file.append({'file': path.name, 'mutable': mutable, 'pinned': pinned,
                         'local': local, 'unknown': unknown, 'reviewed_baseline_limit': maximum})
    return {'ok': not violations, 'violations': violations, 'workflows': len(paths),
            'mutable_refs': mutable_total, 'pinned_refs': pinned_total,
            'unknown_refs': unknown_total, 'local_refs': local_total,
            'files': per_file, 'note': 'Advisory heuristic; use gh actions-lock for real transitive commit locking'}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workflows', type=Path, help='path to .github/workflows')
    parser.add_argument('--baseline', required=True, type=Path,
                        help='reviewed legacy mutable-reference count baseline JSON')
    parser.add_argument('--output', type=Path, default=None, help='optional local JSON report')
    args = parser.parse_args()
    try:
        baseline = json.loads(args.baseline.read_text(encoding='utf-8'))
        report = evaluate_policy(args.workflows, baseline)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f'Actions reference audit FAILED: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    encoded = json.dumps(report, indent=2, ensure_ascii=False)+'\n'
    if args.output:
        args.output.write_text(encoded, encoding='utf-8')
    else:
        print(encoded)
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())