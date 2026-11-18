"""Independent F58 arithmetic verifier (Decimal, no import of F58 analysis code).
Not an independent observation or C-RNS astrophysics run.
"""
from decimal import Decimal, localcontext
import argparse,hashlib,json
from pathlib import Path

F51_SHA='3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d'

def verify(source_path, result_path):
    raw=Path(source_path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=F51_SHA:
        raise ValueError('F51_SHA_256_BAD')
    source=json.loads(raw,parse_float=Decimal)
    result=json.loads(Path(result_path).read_text())
    with localcontext() as context:
        context.prec=45
        w=source['common_radio_prior_mass_fraction_now']
        q=source['remaining_prior_mass_fraction_uncomputed_for_all_seven']
        if abs(w+q-Decimal(1))>Decimal('1e-12'):
            raise ValueError('INCORRECT_PRIOR_PARTITION')
        checks=0
        for key,s in source['surfaces'].items():
            p=result['surfaces'][key]
            scores=s['common_24_direct_root_observational_integrals']
            ordered=sorted(scores, key=lambda k: (-scores[k]['conditional_on_verified_mass_window_L_over_Z'],k))
            a,b=ordered[:2]
            if [a,b]!=[p['in_window_top_model'],p['in_window_runner_up']]:
                raise ValueError('LEADER_RANK_MISMATCH')
            for name,row in scores.items():
                lx=row['conditional_on_verified_mass_window_L_over_Z']
                expected=w*lx
                if abs(expected-row['likelihood_full_radio_prior_window_contribution'])>Decimal('2e-12'):
                    raise ValueError('SOURCE_F51_WINDOW_SCORE_NONREPRODUCIBLE')
                reported=Decimal(str(p['in_window_scores'][name]['in_window_full_prior_contribution']))
                if abs(reported-expected)>Decimal('2e-12'):
                    raise ValueError('F58_WINDOW_MASS_WEIGHTED_SCORE_NOT_REPRODUCIBLE')
                checks+=1
            computed=(w*(scores[a]['conditional_on_verified_mass_window_L_over_Z']-scores[b]['conditional_on_verified_mass_window_L_over_Z']))/q
            reported=Decimal(str(p['min_competitor_extra_unknown_tail_mean_to_reverse_if_leader_tail_is_zero']))
            if abs(computed-reported)>Decimal('2e-12'):
                raise ValueError('F58_RANK_REVERSAL_THRESHOLD_NOT_REPRODUCIBLE')
            checks+=1
            for scenario in p['possible_winner_scenarios']:
                B=Decimal(str(scenario['hypothetical_upper_bound_B_for_every_model_tail_mean_L_over_Z']))
                lower={k:w*v['conditional_on_verified_mass_window_L_over_Z'] for k,v in scores.items()}
                possible=sorted(k for k in scores if lower[k]+q*B>=max(lower.values())-Decimal('1e-12'))
                if possible!=scenario['possible_winners_under_independent_nonnegative_tail_mean']:
                    raise ValueError('F58_TAIL_BOUNDED_POSSIBLE_WINNERS_WRONG')
                checks+=1
        if checks!=6*(7+1+5):
            raise ValueError('AUDIT_CHECK_COUNT_INCOMPLETE')
        return {'status':'PASS_DECIMAL_45_DIGIT_INDEPENDENT_ALGEBRA_RECALCULATION',
                'F51_SHA256':F51_SHA,'F58_result_SHA256':hashlib.sha256(Path(result_path).read_bytes()).hexdigest(),
                'arithmetic_crosschecks':checks,
                'method':'Independent Decimal(45-digit) arithmetic of all six F51 KDE surfaces, 42 weighted source scores and B-bounded winner sets. Not a new astrophysics simulation.',
                'physical_EOS_evidence':'NOT_RUN'}

def main():
    p=argparse.ArgumentParser()
    for k in ('f51','f58','out'):p.add_argument('--'+k,required=True,type=Path)
    v=p.parse_args()
    report=verify(v.f51,v.f58)
    v.out.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report,sort_keys=True))

if __name__=='__main__':main()