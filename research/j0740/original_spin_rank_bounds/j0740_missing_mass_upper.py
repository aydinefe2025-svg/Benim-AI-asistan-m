#!/usr/bin/env python3
"""Certify ranking under *any* F38 source-grid-supported contributions outside
real sampled RNS C mass branches. Does NOT certify physical EOS admissibility.

For the source-defined bilinear F38 density L(m,r), each mass knot j has
U_j=max_r L(m_j,r). For any m between knot j and j+1 and any radius in the
source grid, the bilinear interpolant satisfies
L(m,r) <= (1-t)U_j+t U_{j+1}. Thus integrate this piecewise-linear U(m)
against the original *single* normalized radio mass prior exactly (normal
CDF/PDF antiderivatives) over mass intervals excluded by each saved RNS branch.
No invented radius continuation or repeating the 323 original C stars.
"""
import argparse, hashlib, io, json, zipfile
from pathlib import Path
import numpy as np
from scipy.stats import norm

MU, SD = 2.082, 0.0703
L, H = MU-5*SD, MU+5*SD
Z = norm.cdf(5.)-norm.cdf(-5.)
ORIGINAL_EVIDENCE_SHA = '0306d0ed4b15f25c4831433aecb5f536cefd803082402a31c6461ea6750559bb'
F38_SHA = '4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307'
EXPECTED_ENVELOPE_SHA = '4d7a16e5d6c1eada208ca49da756245a348ae725917a4b1ba77bdeb026815924'
EOS = ('APR4_EPP','ENG','MPA1','MS1','MS1B','WFF1','WFF2')


def sha(b):
    return hashlib.sha256(b).hexdigest()


def integral_gaussian_times_linear(a, b, ya, yb, lo, hi):
    """Exact ∫_lo^hi prior(m) × linear_interpolant(a,ya,b,yb) dm."""
    a,b,lo,hi,ya,yb=map(float,(a,b,lo,hi,ya,yb))
    if not a < b or not 0 <= ya or not 0 <= yb:
        raise ValueError('invalid source knots')
    lo,hi=max(a,lo,L),min(b,hi,H)
    if hi<=lo:return 0.
    zl,zh=(lo-MU)/SD,(hi-MU)/SD
    prob=float((norm.cdf(zh)-norm.cdf(zl))/Z)
    first_moment=MU*prob + SD*(norm.pdf(zl)-norm.pdf(zh))/Z
    slope=(yb-ya)/(b-a)
    # Relative centered mass moment avoids cancellation in large-offset line.
    return float(ya*prob+slope*(first_moment-a*prob))


def max_possible_unseen(masses, envelope, lo, hi):
    """Sharp pointwise source-grid upper on the unknown out-of-branch score."""
    m=np.asarray(masses,dtype=float);y=np.asarray(envelope,dtype=float)
    if m.ndim!=1 or len(m)<5 or y.shape!=m.shape or not np.isfinite(m).all() or not np.isfinite(y).all():
        raise ValueError('malformed F38 mass envelope')
    if np.any(np.diff(m)<=0) or np.any(y<0) or not (0.1 <= lo < hi <= 4.0):
        raise ValueError('invalid mass support')
    total=0.
    for a,b,ya,yb in zip(m[:-1],m[1:],y[:-1],y[1:]):
        # no extrapolation past the defined F38 mass grid
        if a<lo:
            total += integral_gaussian_times_linear(a,b,ya,yb,a,min(b,lo))
        if b>hi:
            total += integral_gaussian_times_linear(a,b,ya,yb,max(a,hi),b)
    if total < -1e-11:
        raise ValueError('numerical upper bound is negative')
    return max(0.,total)


def gaussian_mass_fraction_beyond_interval(lo,hi):
    return float((norm.cdf((min(hi,H)-MU)/SD)-norm.cdf((max(lo,L)-MU)/SD))/Z)


def run(source_zip=None, envelope_data=None):
    if source_zip is None and envelope_data is None:
        raise ValueError('original full source or validated numerical envelope required')
    if source_zip is not None:
        raw=Path(source_zip).read_bytes()
        if sha(raw)!=ORIGINAL_EVIDENCE_SHA:
            raise ValueError('original pinned combined evidence ZIP SHA mismatch')
        with zipfile.ZipFile(io.BytesIO(raw)) as zin:
            if zin.testzip() is not None:raise ValueError('damaged evidence ZIP CRC')
            evidence=json.loads(zin.read('out/J0740_seven_original_RNS_C_full_mass_recovery_20261119.json'))
            raw_f38=zin.read('inputs/J0740_F38_Source_Marginal_Likelihood_20261117.zip')
            if sha(raw_f38)!=F38_SHA:raise ValueError('changed authentic F38 source')
            f38=zipfile.ZipFile(io.BytesIO(raw_f38))
            if f38.testzip() is not None:raise ValueError('F38 CRC')
            archive_envelopes={}
            for key in evidence['rotating_mass_integrated_six_F38']['six_obs']:
                src=np.load(io.BytesIO(f38.read('posterior_prior_ratio_'+key+'.npz')),allow_pickle=False)
                mass=np.asarray(src['mass_centres'],float)
                vals=np.asarray(src['relative_likelihood_L_over_Z'],float)
                if vals.shape!=(401,581) or not np.isfinite(vals).all() or np.any(vals<0):
                    raise ValueError('non-original F38 KDE grid')
                archive_envelopes[key]={'mass_knots_msun':mass.tolist(),'max_radius_likelihood':vals.max(axis=1).tolist(),
                                        'rowmax_float64_sha256':sha(vals.max(axis=1).tobytes()),
                                        'original_grid_shape':[401,581]}
            envelope_data={'source_evidence_sha256':ORIGINAL_EVIDENCE_SHA,'source_f38_sha256':F38_SHA,
                           'source_7_eos_masslines':{k:v['accepted_numeric_source_mass_range_msun'] for k,v in evidence['all_seven_original_rotating_massline_C_sequences'].items()},
                           'six_original_F38_scores':{k:v['unnormalized_score'] for k,v in evidence['rotating_mass_integrated_six_F38']['six_obs'].items()},
                           'six_F38_source_rowmax_envelopes':archive_envelopes}
    full_env_hash=sha(json.dumps(envelope_data,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf8'))
    if full_env_hash!=EXPECTED_ENVELOPE_SHA:
        raise ValueError('original empirical F38 envelope and RNS score bytes do not match source pinned fingerprint')
    if envelope_data['source_evidence_sha256']!=ORIGINAL_EVIDENCE_SHA or envelope_data['source_f38_sha256']!=F38_SHA:
        raise ValueError('not source-matched')
    if set(envelope_data['source_7_eos_masslines'])!=set(EOS):raise ValueError('EOS identity changed')
    if len(envelope_data['six_original_F38_scores'])!=6 or set(envelope_data['six_original_F38_scores'])!=set(envelope_data['six_F38_source_rowmax_envelopes']):
        raise ValueError('F38 source variant mismatch')
    runs={}; winner_margins=[]
    for name, score in envelope_data['six_original_F38_scores'].items():
        if set(score)!=set(EOS) or not all(np.isfinite(float(v)) and v>0 for v in score.values()):
            raise ValueError('invalid original empirical source scores')
        env=envelope_data['six_F38_source_rowmax_envelopes'][name]
        m=env['mass_knots_msun'];u=env['max_radius_likelihood']
        if sha(np.asarray(u,dtype=np.float64).tobytes())!=env['rowmax_float64_sha256']:
            raise ValueError('F38 original row-wise radius maximum SHA mismatch')
        if len(m)!=401 or len(u)!=401 or not 1.73 < m[0] < 1.74 or not 2.43 < m[-1] < 2.44:
            raise ValueError('invalid original source mass grid')
        bounds={}
        for eos in EOS:
            lo,hi=envelope_data['source_7_eos_masslines'][eos]
            bound=max_possible_unseen(m,u,lo,hi)
            bounds[eos]=bound
        total=sum(score.values()); excess=sum(bounds.values())
        share={eos:{'baseline_conditional':score[eos]/total,
                    'minimum_under_arbitrary_unseen_F38_likelihood':score[eos]/(total+excess-bounds[eos]),
                    'maximum_under_arbitrary_unseen_F38_likelihood':(score[eos]+bounds[eos])/(total+bounds[eos])} for eos in EOS}
        # This checks the *stronger*, unnormalized score partial identification;
        # adding any missing nonnegative contributions cannot reverse pairs that pass.
        all_rivals={eos:float(score['MPA1']-score[eos]-bounds[eos]) for eos in EOS if eos!='MPA1'}
        eng_margin_to_others={eos:float(score['ENG']-score[eos]-bounds[eos]) for eos in EOS if eos not in ('MPA1','ENG')}
        apr_margin_to_others={eos:float(score['APR4_EPP']-score[eos]-bounds[eos]) for eos in EOS if eos not in ('MPA1','ENG','APR4_EPP')}
        runs[name]={'observed_scores':{eos:float(score[eos]) for eos in EOS},
                    'mathematically_max_additional_missing_mass_scores':bounds,
                    'conditional_probability_bounds':share,
                    'MPA1_minus_every_other_maximal_score':all_rivals,
                    'ENG_minus_every_other_lower_rank_maximal_score':eng_margin_to_others,
                    'APR4_minus_lower_rank_maximal_score':apr_margin_to_others,
                    'source_F38_mass_grid_max_likelihood':max(u)}
        winner_margins.append(min(all_rivals.values()))
    verified_winners=all(min(r['MPA1_minus_every_other_maximal_score'].values())>0 for r in runs.values())
    second_place=all(min(r['ENG_minus_every_other_lower_rank_maximal_score'].values())>0 for r in runs.values())
    third_place=all(min(r['APR4_minus_lower_rank_maximal_score'].values())>0 for r in runs.values())
    return {'schema':'J0740_SEVEN_ORIGINAL_SPIN_GR_F38_UNCOMPUTED_MASS_SHARP_SOURCE_ENVELOPE_V1',
            'physics_scope':'7 source-original rotating GR RNS massline KDE comparison only, NOT physically certified EOS posterior',
            'method':'original F38 bilinear source KDE row max in radius at each mass; exact analytic Gaussian×linear mass-integral over uncomputed real-RNS support; excludes F38 interpolation exterior',
            'status':'ALL_SIX_F38_CONDITIONAL_RANK_1_2_3_ROBUST_TO_ARBITRARY_MISSING_BRANCHES' if verified_winners and second_place and third_place else 'SOME_CONDITIONAL_RANK_NOT_CERTIFIED',
            'all_six_MPA1_rank1':verified_winners,'all_six_ENG_rank2':second_place,'all_six_APR4_rank3':third_place,
            'minimum_MPA1_score_advantage_over_any_maximal_competitor':min(winner_margins),
            'six_kde_upper_bounds':runs,
            'physical_certification':'NOT_ESTABLISHED',
            'source_native_photon_XPSI_Bayes':'NOT_RUN',
            'source_evidence_sha256':ORIGINAL_EVIDENCE_SHA,
            'source_f38_sha256':F38_SHA},envelope_data


def main():
    p=argparse.ArgumentParser();p.add_argument('--original-evidence-zip',type=Path);p.add_argument('--envelopes',type=Path);p.add_argument('--outdir',type=Path,required=True)
    a=p.parse_args();en=json.loads(a.envelopes.read_text()) if a.envelopes else None
    result,envelopes=run(a.original_evidence_zip,en)
    a.outdir.mkdir(parents=True,exist_ok=True)
    (a.outdir/'J0740_seven_missing_mass_rank_certificate.json').write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
    if a.original_evidence_zip:
        (a.outdir/'J0740_source_F38_rows_max_envelopes.json').write_text(json.dumps(envelopes,separators=(',',':'),sort_keys=True,allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k in ('status','all_six_MPA1_rank1','all_six_ENG_rank2','all_six_APR4_rank3','minimum_MPA1_score_advantage_over_any_maximal_competitor')},indent=2))

if __name__=='__main__':main()
