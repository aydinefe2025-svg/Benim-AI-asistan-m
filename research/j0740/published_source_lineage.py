"""Byte-pinned, publisher-documented Salmi 2024 headline source-run identity.

This is not an X-PSI likelihood run, EOS evidence, or a new 12.9 GB archive audit.
Original full/posterior archive MD5 values are historical pinned metadata only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

EXPECTED = {
    'runner': ('STU/STU_NICER_XMM_hr/STU_modules/main_lp40k_Xse001_Dfix.py', '440451fd57c8d8c775f3c847861d6fce77a82ab975ca090fb660289191d8c1af'),
    'prior': ('STU/STU_NICER_XMM_hr/STU_modules/CustomPrior_GLS_compressed_scaling_Dfix.py', 'ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93'),
    'config': ('STU/STU_NICER_XMM_hr/STU_modules/config.ini', '02592091e8c10d126b10070e0e33515a292d57d750c2a45d624065d056752ede'),
    'out_log': ('STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/out_', 'f20ae7db9550a9fd608542c1b43fc9534a3e396df7ef5c2dad66493793caa2de'),
    'stats': ('STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/stu_nlive40000_eff0.01_noCONST_noMM_noIS_tol-1stats.dat', '779167d6d11e40d21eb733523e4759773ef1e1f9eb913227e8550d7dd30f5b14'),
}
README_MD5 = 'ed363c6d252a0a6ef177f8d45757e50e'
POSTERIOR_MEMBER = 'mr_samples_and_contours/J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat'
POSTERIOR_SUBSET_SHA256 = '4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b'
POSTERIOR_ARCHIVE_MD5 = 'ca8e70eeca81feb71321f1a88a24f2f9'
FULL_ARCHIVE_MD5 = '7792c92b9ae1fa404ae5bdd3920ce075'
KNOWN_LOGZ = -21889.986812013929
KNOWN_LOGZ_ERROR = 0.0244091345940078905
PROOF_LABEL = 'publisher_readme_headline_stu_directory_and_pinned_original_bytes'

class SourceBindingError(ValueError):
    """Input does not establish the required publisher/run linkage."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_published_headline_manifest(manifest_path: str | Path, *,
                                       expected_hashes: Mapping[str, str] | None = None,
                                       allow_synthetic_test: bool = False) -> dict:
    """Check pinned source files without demanding 'gamma_NxX' inside ST-U config.

    expected_hashes override is exclusively for synthetic unit tests. It is
    prohibited unless allow_synthetic_test=True and can NEVER yield real PASS.
    """
    synthetic = expected_hashes is not None
    if synthetic and not allow_synthetic_test:
        raise SourceBindingError('test pins may not be used in a real source audit')
    pins = {role: digest for role, (_, digest) in EXPECTED.items()}
    if synthetic:
        if set(expected_hashes) != set(EXPECTED):
            raise SourceBindingError('invalid fixture pin set')
        pins = dict(expected_hashes)
    path = Path(manifest_path)
    m = json.loads(path.read_text(encoding='utf-8'))
    required = {
        'schema': 'j0740-publisher-headline-v2',
        'binding_proof': PROOF_LABEL,
        'published_readme_md5': README_MD5,
        'posterior_member': POSTERIOR_MEMBER,
        'posterior_subset_sha256': POSTERIOR_SUBSET_SHA256,
        'posterior_archive_md5': POSTERIOR_ARCHIVE_MD5,
        'full_archive_md5': FULL_ARCHIVE_MD5,
    }
    for k, value in required.items():
        if m.get(k) != value:
            raise SourceBindingError(f'manifest {k} missing or mismatched')
    entries = m.get('artifacts')
    if not isinstance(entries, dict) or set(entries) != set(EXPECTED):
        raise SourceBindingError('missing/extra source artifact roles')
    for role, (member, _) in EXPECTED.items():
        record = entries[role]
        if not isinstance(record, dict):
            raise SourceBindingError(f'{role}: malformed record')
        if record.get('original_archive_member', '').replace('\\', '/') != member:
            raise SourceBindingError(f'{role}: wrong published archive member')
        if record.get('sha256') != pins[role]:
            raise SourceBindingError(f'{role}: not the pinned original file SHA256')
        raw_path = record.get('local_path')
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise SourceBindingError(f'{role}: missing local file path')
        local = Path(raw_path).expanduser()
        if not local.is_absolute():
            local = path.parent / local
        if not local.is_file() or _sha256(local) != pins[role]:
            raise SourceBindingError(f'{role}: original byte identity fails')
    log_path = Path(entries['out_log']['local_path']).expanduser()
    if not log_path.is_absolute():
        log_path = path.parent / log_path
    log = log_path.read_text(encoding='utf-8', errors='replace')
    match = re.search(r'(?im)\bX[\s-]?PSI\b[^\r\n]{0,90}?\bv?(\d+\.\d+\.\d+)\b', log)
    if not match:
        raise SourceBindingError('original out_ log contains no X-PSI version')
    version = tuple(map(int, match.group(1).split('.')))
    if not ((0, 7, 10) <= version <= (1, 2, 1)):
        raise SourceBindingError('X-PSI version outside README documented range')
    if m.get('xpsi_version') != 'v' + match.group(1):
        raise SourceBindingError('X-PSI manifest version differs from pinned log')
    for label in ('stats', 'out'):
        val = m.get('reported_evidence', {}).get(label)
        if not isinstance(val, dict):
            raise SourceBindingError('missing published evidence pair')
        for key, expected, tol in (('logz', KNOWN_LOGZ, 1e-8), ('error', KNOWN_LOGZ_ERROR, 1e-10)):
            if not isinstance(val.get(key), (int, float)) or abs(val[key] - expected) > tol:
                raise SourceBindingError(f'{label}: published {key} mismatch')
    return {
        'status': 'SYNTHETIC_TEST_ONLY' if synthetic else 'PUBLISHER_DIRECTORY_AND_PINNED_SOURCE_BYTES_VERIFIED',
        'posterior_to_STU_mapping': 'PUBLISHED_README_DOCUMENTED',
        'source_bytes_checked_this_run': True,
        'full_12p9GB_archive_rehashed_this_run': False,
        'posterior_archive_rehashed_this_run': False,
        'historical_full_archive_md5_from_manifest': FULL_ARCHIVE_MD5,
        'xpsi_version_from_pinned_out_log': 'v' + match.group(1),
        'native_photon_likelihood_recomputed': False,
        'source_posterior_recomputed': False,
        'EOS_Bayes': 'NOT_RUN',
        'caution': 'No evidence of actual historical execution from matching names and file bytes alone; no valid EOS Bayes factors.',
    }