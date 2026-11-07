"""Audit four SMALL original Salmi 2024 headline-run files, not EOS evidence.

Reads a previously owned Salmi tar.gz sequentially (never downloads), extracts
ONLY the source runner, matching prior, sampler config and one actual out_ log.
Fails closed for ambiguous/missing inputs; reports source SHA256 and provenance.
A local extracted-folder audit is DIAGNOSTIC ONLY; its files alone do not prove
that their bytes belong to the publisher's original 12.9GB archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

from source_lineage_gate import (
    SOURCE_POSTERIOR_SHA256, SOURCE_POSTERIOR_MEMBER, SOURCE_POSTERIOR_RUN,
    SOURCE_POSTERIOR_ARCHIVE_MD5, SOURCE_FULL_ARCHIVE_MD5,
    PUBLISHED_HEADLINE_RUNNER, PUBLISHED_HEADLINE_PRIOR,
    PUBLISHED_HEADLINE_OUTPUT_DIR, RunLineageNotProven,
    verify_matched_run_manifest,
)

BASE = "STU/STU_NICER_XMM_hr/"
CONFIG_NAME = "config_postprocess_J0740_gamma.ini"
ROLE_MAX_BYTES = {
    'matching_prior': 2_000_000,
    'matching_runner': 2_000_000,
    'matching_sampler_config': 2_000_000,
    'matching_run_log': 12_000_000,
}


def canonical_member(raw: str) -> str:
    """Allow publisher's optional J0740_GAMMA_zenodo prefix but no traversal."""
    norm = raw.replace('\\', '/')
    parts = PurePosixPath(norm).parts
    if not parts or norm.startswith('/') or '..' in parts or ':' in norm:
        raise ValueError(f'Unsafe archive member name: {raw!r}')
    if parts[0] == 'J0740_GAMMA_zenodo':
        parts = parts[1:]
    return '/'.join(p for p in parts if p != '.')


def classify(original_name: str, log_name: str | None = None) -> str | None:
    p = canonical_member(original_name)
    if p == PUBLISHED_HEADLINE_RUNNER:
        return 'matching_runner'
    if p == PUBLISHED_HEADLINE_PRIOR:
        return 'matching_prior'
    # Avoid guessing a config from another sampling run.
    if p == BASE + 'STU_modules/' + CONFIG_NAME:
        return 'matching_sampler_config'
    if p.startswith(PUBLISHED_HEADLINE_OUTPUT_DIR) and PurePosixPath(p).name.startswith('out_'):
        name = PurePosixPath(p).name
        if log_name is None or log_name == name:
            return 'matching_run_log'
    return None


def discover_archive(archive: Path, *, log_name: str | None = None) -> dict[str, tuple[str, bytes]]:
    """One read-only streaming scan of existing gzip tar, no whole extraction."""
    selected: dict[str, tuple[str, bytes]] = {}
    with tarfile.open(archive, mode='r|gz') as tf:
        for member in tf:
            role = classify(member.name, log_name)
            if role is None:
                continue
            if not member.isfile() or member.size > ROLE_MAX_BYTES[role]:
                raise RunLineageNotProven(f'Unsafe or oversized target {role}')
            if role in selected:
                raise RunLineageNotProven(f'Ambiguous duplicate {role}: {selected[role][0]} and {member.name}')
            stream = tf.extractfile(member)
            if stream is None:
                raise RunLineageNotProven(f'Cannot open original {role}')
            data = stream.read(ROLE_MAX_BYTES[role] + 1)
            if len(data) != member.size or len(data) > ROLE_MAX_BYTES[role]:
                raise RunLineageNotProven(f'Truncated or oversized original {role}')
            selected[role] = member.name, data
    return selected


def discover_directory(root: Path, *, log_name: str | None = None) -> dict[str, tuple[str, bytes]]:
    selected: dict[str, tuple[str, bytes]] = {}
    root = root.resolve()
    for candidate in root.rglob('*'):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        rel = candidate.relative_to(root).as_posix()
        role = classify(rel, log_name)
        if role is None:
            continue
        if candidate.stat().st_size > ROLE_MAX_BYTES[role]:
            raise RunLineageNotProven(f'Oversized extracted {role}')
        if role in selected:
            raise RunLineageNotProven(f'Ambiguous extracted {role}: two candidates')
        selected[role] = rel, candidate.read_bytes()
    return selected


def build_report(selected: dict[str, tuple[str, bytes]], output: Path, *, actual_archive: bool,
                 expected_runner_sha256: str | None = None,
                 expected_prior_sha256: str | None = None) -> dict:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    records = {}
    for role in ROLE_MAX_BYTES:
        if role not in selected:
            records[role] = {'status': 'MISSING', 'required': True}
            continue
        name, data = selected[role]
        hashval = hashlib.sha256(data).hexdigest()
        target = output / (role + ('.txt' if role == 'matching_run_log' else '.source'))
        target.write_bytes(data)
        records[role] = {'status':'FOUND', 'original_archive_member':canonical_member(name),
                         'actual_tar_member_name':name,
                         'sha256':hashval, 'bytes':len(data), 'local_path':str(target)}

    # Nonempty condition: old F30 ZIP files are independent sources; direct
    # SHA comparison is evidence but does not establish sample/likelihood parity.
    for role, expected in [('matching_runner', expected_runner_sha256),
                           ('matching_prior', expected_prior_sha256)]:
        if expected is not None and records[role]['status'] == 'FOUND':
            records[role]['matches_existing_F30_source_sha256'] = (records[role]['sha256'] == expected)

    issues = [f'{role}:missing' for role, record in records.items() if record['status'] != 'FOUND']
    for role, expected in [('matching_runner', expected_runner_sha256),
                           ('matching_prior', expected_prior_sha256)]:
        if expected is not None and records[role].get('status') == 'FOUND' and \
                not records[role].get('matches_existing_F30_source_sha256', False):
            issues.append(f'{role}:original_sha_differs_from_recovered_F30')
    runner = selected.get('matching_runner', ('', b''))[1].decode('utf-8',errors='replace')
    config = selected.get('matching_sampler_config', ('', b''))[1].decode('utf-8',errors='replace')
    log = selected.get('matching_run_log', ('', b''))[1].decode('utf-8',errors='replace')
    if runner and 'from CustomPrior_GLS_compressed_scaling_Dfix import CustomPrior' not in runner:
        issues.append('runner_prior_import_not_confirmed')
    if config and SOURCE_POSTERIOR_RUN not in config:
        issues.append('sampler_config_exact_posterior_label_absent')
    if log and not re.search(r'(?im)\bX[\s-]?PSI\b[^\r\n]{0,90}?\bv?\d+\.\d+\.\d+\b',log):
        issues.append('out_log_xpsi_version_not_identifiable')
    if not actual_archive:
        issues.append('extracted_directory_not_cryptographically_attached_to_original_tar')

    info = {
        'status':'PROVENANCE_DIAGNOSTIC_ONLY_NOT_EOS_EVIDENCE',
        'source': 'publisher_archive_member_bytes' if actual_archive else 'previously_extracted_directory_unlinked',
        'source_full_archive_md5_previously_reported_not_recomputed':SOURCE_FULL_ARCHIVE_MD5,
        'original_posterior_member':SOURCE_POSTERIOR_MEMBER,
        'selected':records, 'issues':issues,
        'strict_lineage_verified':False,
        'scientific_note':'Never implies native 15D nuisance, photon likelihood, or model evidence',
    }
    # Produce manifest only for original tar members when prerequisite labels
    # are present. It is not evidence until independently checked by gate.
    if actual_archive and not issues:
        m = {
            'provenance_schema':'j0740-gamma-nxx-run-match-v1',
            'posterior_subset_sha256': SOURCE_POSTERIOR_SHA256,
            'posterior_source_member': SOURCE_POSTERIOR_MEMBER,
            'posterior_run': SOURCE_POSTERIOR_RUN,
            'full_archive_md5': SOURCE_FULL_ARCHIVE_MD5,
            'source_archive_md5': SOURCE_POSTERIOR_ARCHIVE_MD5,
            'verified_run_identity':'exact_gamma_NxX_lp40k_se001_source_and_prior',
            'binding_proof':'source_sampler_configuration_names_exact_posterior_run',
        }
        m.update(records)
        match = re.search(r'(?im)\bX[\s-]?PSI\b[^\r\n]{0,90}?\bv?(\d+\.\d+\.\d+)\b',log)
        m['xpsi_version'] = 'v' + match.group(1)
        mpath = output/'matched_run_manifest_candidate.json'
        mpath.write_text(json.dumps(m,ensure_ascii=False,sort_keys=True,indent=2)+'\n', encoding='utf-8')
        try:
            gate=verify_matched_run_manifest(mpath)
        except (ValueError,KeyError) as exc:
            issues.append('strict_lineage_gate_rejected:' + str(exc))
            mpath.unlink()
        else:
            info['strict_lineage_verified']=True
            info['lineage_gate_status']=gate['status']
            info['candidate_manifest_path']=str(mpath)
    info['issues']=issues
    (output/'source_run_probe_report.json').write_text(json.dumps(info,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    group=p.add_mutually_exclusive_group(required=True)
    group.add_argument('--archive',type=Path,help='ALREADY DOWNLOADED Salmi tar.gz; only 4 small members are copied')
    group.add_argument('--extracted-root',type=Path,help='Existing 165 extracted text files; diagnostic only')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--log-name',help='Exact out_ filename; required if more than one matches')
    p.add_argument('--expect-runner-sha256',default='0a1f9a8e2c6b7c73cf929600fd6867e7637ca6759f16459df87e071165669000')
    p.add_argument('--expect-prior-sha256',default='5ebcf0a2f11a0f159860ec740e719957066521a501a02c889c5e3da9063207da')
    args=p.parse_args()
    if args.log_name and (not args.log_name.startswith('out_') or '/' in args.log_name or '\\' in args.log_name):
        p.error('--log-name must be one simple out_ basename')
    for required in (args.archive,args.extracted_root):
        if required and not required.is_file() and not required.is_dir():
            p.error(f'Path does not exist: {required}')
    selected=(discover_archive(args.archive,log_name=args.log_name) if args.archive
              else discover_directory(args.extracted_root,log_name=args.log_name))
    report=build_report(selected,args.out,actual_archive=bool(args.archive),
                        expected_runner_sha256=args.expect_runner_sha256,
                        expected_prior_sha256=args.expect_prior_sha256)
    print(json.dumps({'status':report['status'],'strict_lineage_verified':report['strict_lineage_verified'],
                      'issues':report['issues'],'report':str(args.out/'source_run_probe_report.json')},ensure_ascii=False))
    if report['issues']:
        raise SystemExit(2)

if __name__=='__main__':main()