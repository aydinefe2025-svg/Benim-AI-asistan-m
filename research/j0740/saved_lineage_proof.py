"""Reconcile the already-verified F31/F32 Salmi source evidence.

Does NOT re-open the 12.9 GB source archive, run X-PSI, or compute EOS evidence.
This removes an obsolete source-run-link blocker without changing source physics.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

F31_NAME = 'J0740_F31_Source_Provenance_20261117.json'
F32_NAME = 'J0740_F32_Weighted_Run_Identity_20261117.json'
F31_SHA = 'e9894f18549c95964ed5bf0f4874f9c9d01db85c5a17c076b569e29d2e9a4278'
F32_SHA = 'b3ecdb8cb49f105751fb36ba8bb87cecc0f9b060414b77efa37a789e3d4c6006'
F31_ZIP_SHA = '46955ddcd923f599c5970eca692bf859b3d4628124e9ab69ab4022f727916638'
F32_ZIP_SHA = '0d3d5c7ff42c3314a77ca896695a83e82639e5da42486b2a4001de61703bc14b'
POST_SHA = '4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b'
RUN = 'STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix'
EXPECTED_MEMBERS = {
 'prior': ('STU/STU_NICER_XMM_hr/STU_modules/CustomPrior_GLS_compressed_scaling_Dfix.py', 'ecabb879c38d4e4e343e5e304e1be39d87a7b0a35d7077454e4677ea1458aa93'),
 'runner': ('STU/STU_NICER_XMM_hr/STU_modules/main_lp40k_Xse001_Dfix.py', '440451fd57c8d8c775f3c847861d6fce77a82ab975ca090fb660289191d8c1af'),
 'config': ('STU/STU_NICER_XMM_hr/STU_modules/config.ini', '02592091e8c10d126b10070e0e33515a292d57d750c2a45d624065d056752ede'),
 'out': ('STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/out_', 'f20ae7db9550a9fd608542c1b43fc9534a3e396df7ef5c2dad66493793caa2de'),
}
STATS_SHA = '779167d6d11e40d21eb733523e4759773ef1e1f9eb913227e8550d7dd30f5b14'
WEIGHTED_N = 1137394
POSTERIOR_TAR_MD5 = 'ca8e70eeca81feb71321f1a88a24f2f9'
TOL = 2e-12

class SavedLineageError(ValueError):
    pass


def _read_pinned(path: Path, sha: str):
    if not path.is_file():
        raise SavedLineageError(f'missing archived source receipt: {path.name}')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise SavedLineageError(f'{path.name}: archived receipt hash mismatch')
    try:
        return json.loads(data)
    except (ValueError, UnicodeDecodeError) as e:
        raise SavedLineageError('archived receipt invalid JSON') from e


def verify_saved_source_lineage(folder: Path | str) -> dict:
    """Verify pinned archival receipts and full 4-moment/4-source crosswalk.

    Original source bytes were independently verified on Windows in F31;
    F32 compared original weighted Salmi samples to run1 stats. This function
    verifies the immutable *receipts*, not historical original raw bytes again.
    """
    root = Path(folder)
    f31 = _read_pinned(root / F31_NAME, F31_SHA)
    f32 = _read_pinned(root / F32_NAME, F32_SHA)
    scan = f31.get('original_archive_member_scan', {})
    if scan.get('status') != 'PASS_4_OF_4_EXACT_MEMBER_SHA256_MATCH':
        raise SavedLineageError('F31 historical original byte scan did not pass')
    if scan.get('tar_members_visited_before_all_found') != 263:
        raise SavedLineageError('F31 source scan is not the pinned 263-member report')
    entries = scan.get('members', {})
    if set(entries) != set(EXPECTED_MEMBERS):
        raise SavedLineageError('F31 source roles missing/extra')
    for role, (suffix, sha) in EXPECTED_MEMBERS.items():
        v = entries[role]
        if v.get('sha256') != sha or not str(v.get('member','')).replace('\\','/').endswith(suffix):
            raise SavedLineageError(f'F31 original {role} member mismatch')
    if not f31.get('historic_F30_code_comparison',{}).get('ast_unparse_same_for_prior_and_runner'):
        raise SavedLineageError('F31 copied code not semantically checked')
    f32s = f32.get('source_code_provenance',{})
    if (not f32s.get('original_tar_members_4_of_4_sha_pass') or
        f32s.get('original_prior_sha256') != EXPECTED_MEMBERS['prior'][1] or
        f32s.get('original_runner_sha256') != EXPECTED_MEMBERS['runner'][1]):
        raise SavedLineageError('F31/F32 original source contradiction')
    sample = f32.get('observational_source',{})
    weighted = f32.get('weighted_posterior_moments',{})
    stats = f32.get('original_run1_multinest_stats_moments',{})
    if sample.get('archive_md5') != POSTERIOR_TAR_MD5 or weighted.get('count') != WEIGHTED_N:
        raise SavedLineageError('original weighted Salmi posterior identifier mismatch')
    if not abs(float(weighted.get('sum_weight', -1)) - 1) < 1e-8:
        raise SavedLineageError('weighted source unnormalised')
    d = {}
    for k in ('mean_mass_msun','std_mass_msun','mean_radius_km','std_radius_km'):
        if not isinstance(weighted.get(k), (float,int)) or not isinstance(stats.get(k), (float,int)):
            raise SavedLineageError('missing weighted/sample stats moment')
        d[k] = float(weighted[k]) - float(stats[k])
        if not math.isfinite(d[k]) or abs(d[k]) >= TOL:
            raise SavedLineageError(f'original weighted posterior vs run1 {k} mismatch')
    if f32.get('max_absolute_moment_delta',math.inf) >= TOL:
        raise SavedLineageError('published F32 four moment acceptance failed')
    matched = f32.get('run_stats_source',{})
    if (matched.get('run_directory') != RUN or
        matched.get('out_sha256') != EXPECTED_MEMBERS['out'][1] or
        matched.get('stats_sha256') != STATS_SHA or
        matched.get('out_banner_version') != '1.2.0'):
        raise SavedLineageError('F32 run1 out/stats identity changed')
    if (abs(matched.get('out_evidence_lnZ',math.inf)-matched.get('stats_evidence_lnZ',-math.inf)) >= 1e-8 or
        abs(matched.get('out_evidence_error',math.inf)-matched.get('stats_evidence_error',-math.inf)) >= 1e-12):
        raise SavedLineageError('X-PSI source log and run1 stats disagree')
    alternative = f32.get('comparison_candidates', [])
    recognized = [x for x in alternative if abs(x.get('delta_mass_mean_vs_published_weighted',math.inf)) < 1e-10 and abs(x.get('delta_radius_mean_km_vs_published_weighted',math.inf)) < 1e-10]
    if len(alternative) != 9 or len(recognized) != 1 or recognized[0]['name'] != 'run1_lp40k_Xse001_Dfix':
        raise SavedLineageError('F32 cross-run unique identity not established')
    return {
      'status':'ARCHIVED_4_SOURCE_BYTES_AND_4_WEIGHTED_MOMENTS_RUN1_ASSOCIATION_VERIFIED',
      'source_prior_run_match':'SUPPORTED_BY_ORIGINAL_F31_F32_ARCHIVED_PRIMARY_PROOFS',
      'original_tar_read_now':False,
      'archived_source_byte_checks_replayed':True,
      'source_posterior_sha256':POST_SHA,
      'archived_source_run':RUN,
      'original_source_sha256':{role:sha for role,(_,sha) in EXPECTED_MEMBERS.items()},
      'original_stats_sha256':STATS_SHA,
      'absolute_moment_residuals':d,
      'max_abs_moment_residual':max(abs(x) for x in d.values()),
      'xpsi_original_run1_log_version':'1.2.0',
      'published_headline_version':'1.2.1',
      'resume_final_engine_version':'UNRESOLVED',
      'source_native_15d_prior_runtime':'NOT_RUN',
      'xpsi_photon_likelihood':'NOT_RUN',
      'seven_original_eos_bayes':'NOT_RUN',
      'input_f31_sha256':F31_SHA,'input_f32_sha256':F32_SHA,
      'original_library_zip_sha256':{'F31':F31_ZIP_SHA,'F32':F32_ZIP_SHA},
    }


if __name__ == '__main__':
    import argparse
    a=argparse.ArgumentParser()
    a.add_argument('--receipts-dir',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True)
    opts=a.parse_args()
    out=verify_saved_source_lineage(opts.receipts_dir)
    opts.output.parent.mkdir(parents=True,exist_ok=True)
    opts.output.write_text(json.dumps(out,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(out,sort_keys=True,indent=2))
