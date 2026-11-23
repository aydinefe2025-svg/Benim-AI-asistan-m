"""V4 reproducible virtual experiment: three independently instrumented trust domains.

Fixture HMACs do not imply a real hardware sync pulse exists. A complete
A/B/C compromise remains information-theoretically indistinguishable.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import json
from pathlib import Path
from research.battery_curve_audit import graz_virtual_lab as v
from research.battery_curve_audit import graz_clock_anchor_gate as two
from research.battery_curve_audit import graz_third_reference_gate as three

SCENARIOS=(
    'nominal_three_roots','electrical_dropout_20pct','electrical_dropout_60pct',
    'two_clock_roots_correlated_compromise','all_three_reference_domains_compromised',
    'missing_external_trigger','wrong_trigger_signature','replayed_trigger_session',
    'modified_stream_after_signature','trigger_uncertainty_high','shared_trigger_key',
    'missing_phase_provenance','wrong_physical_cell','three_second_unattested_offset'
)
EXPECTED_NEGATIVE={
    'two_clock_roots_correlated_compromise','missing_external_trigger',
    'wrong_trigger_signature','replayed_trigger_session','modified_stream_after_signature',
    'trigger_uncertainty_high','shared_trigger_key','missing_phase_provenance',
    'wrong_physical_cell','three_second_unattested_offset'
}


def run(*,seeds:int=12,seed_start:int=20261123)->dict:
    if isinstance(seeds,bool) or not isinstance(seeds,int) or not 1<=seeds<=200:
        raise ValueError('bounded positive seeds required')
    output=[]
    for scenario in SCENARIOS:
        a={'scenario':scenario,'synthetic_sensor_samples':0,'accepted':0,
           'wrong_time_accepted':0,'denied_gates':0,'passed_gates':0,'physical_release_allowed':False}
        for seed in range(seed_start,seed_start+seeds):
            for cell,preload in v.PRELOADS_KN.items():
                offset=3. if scenario in ('two_clock_roots_correlated_compromise',
                  'all_three_reference_domains_compromised','three_second_unattested_offset') else .2
                drop=.2 if scenario=='electrical_dropout_20pct' else (.6 if scenario=='electrical_dropout_60pct' else .05)
                synthetic_seed=seed+int(cell)*100000
                e,s=v.generate_synthetic(cell,synthetic_seed,preload_kN=preload,
                       clock_offset_s=offset,electric_drop=drop,cell_id_valid=scenario!='wrong_physical_cell')
                session_id=f'V4-SYN-{seed}-{cell}'
                corrupted_ab=scenario in ('two_clock_roots_correlated_compromise','all_three_reference_domains_compromised')
                anchors,roots=two.mock_independent_witnesses(seed=synthetic_seed,
                    session_id=session_id,cell_id=cell,truth_first_t=s[0].truth_t,
                    clock_offset_s=offset,correlated_fake_reference=corrupted_ab)
                pulses,third_key=three.mock_independent_pulses(seed=synthetic_seed,
                    session_id=session_id,cell_id=cell,truth_first_t=s[0].truth_t,
                    clock_offset_s=offset,electric=e,sensors=s,
                    correlated_fake_reference=scenario=='all_three_reference_domains_compromised')
                if scenario=='missing_external_trigger':pulses=[]
                elif scenario=='wrong_trigger_signature':
                    pulses[0]=replace(pulses[0],mac_hex='0'*64)
                elif scenario=='replayed_trigger_session':
                    pulses=[replace(p,session_id='EARLIER-SESSION') for p in pulses]
                elif scenario=='modified_stream_after_signature':
                    s=[replace(s[0],sensor_um=(s[0].sensor_um[0]+3,*s[0].sensor_um[1:])),*s[1:]]
                elif scenario=='trigger_uncertainty_high':
                    raw=replace(pulses[0],uncertainty_s=.3,mac_hex='')
                    pulses[0]=three.sign_pulse(raw,signing_key=third_key)
                elif scenario=='shared_trigger_key':
                    third_key=roots[two.ANCHOR_ISSUERS[0]]
                res=three.verify_and_join_three_reference(e,s,anchors=anchors,trust_roots=roots,
                    pulses=pulses,trigger_key=third_key,session_id=session_id,
                    expected_cell=cell,reference_bounds=(s[0].truth_t,s[0].truth_t+1200.),
                    phase_source_authentic=scenario!='missing_phase_provenance')
                a['synthetic_sensor_samples']+=len(s)
                a['accepted']+=res['accepted']
                a['wrong_time_accepted']+=res['wrong_time_accepted']
                a['denied_gates']+=int(not res['gate_passed'])
                a['passed_gates']+=int(res['gate_passed'])
                assert not res['physical_production_release_allowed']
        assert a['synthetic_sensor_samples']==seeds*len(v.PRELOADS_KN)*240
        if scenario in EXPECTED_NEGATIVE:
            assert a['accepted']==0 and a['wrong_time_accepted']==0,(scenario,a)
        elif scenario=='all_three_reference_domains_compromised':
            assert a['wrong_time_accepted']>0 and a['accepted']>0,(scenario,a)
        else:
            assert a['accepted']>0 and a['wrong_time_accepted']==0,(scenario,a)
        output.append(a)
    return {
        'goal_key':'graz-20261123-third-independent-trigger-simulation-v4',
        'simulation_only':True,'independent_real_hardware_available':False,
        'external_controller_phase_certificate_available':False,
        'current_units_from_original_source_verified':False,
        'original_source_doi_reference':'10.5281/zenodo.22079387',
        'original_zip_sha256_reference':v.REAL_SOURCE_SHA256,
        'real_source_reprocessed':False,
        'physical_production_release_allowed':False,
        'seeds':seeds,'seed_start':seed_start,
        'distinct_virtual_cells':list(v.PRELOADS_KN),
        'scenarios':output,
        'total_synthetic_samples':sum(x['synthetic_sensor_samples'] for x in output),
        'finding':'Two compromised original clock roots are detectible conditional on truly independent third physical trigger; all three jointly compromised remain underdetermined.',
        'physically_verified_claims':[],
        'independent_real_corroboration_missing':['third calibrated physical trigger and its key provenance',
            'raw device clock and trigger correlation','actual controller phase program',
            'current units and measurement calibration','absolute displacement calibration',
            'true repeated physical specimens','FEA mesh convergence/dynamic impact testing'],
    }

def main()->None:
    p=argparse.ArgumentParser();p.add_argument('output',type=Path)
    p.add_argument('--seeds',type=int,default=12);p.add_argument('--seed-start',type=int,default=20261123)
    args=p.parse_args()
    result=run(seeds=args.seeds,seed_start=args.seed_start)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    for r in result['scenarios']:
        print(r['scenario'],r['synthetic_sensor_samples'],r['accepted'],r['wrong_time_accepted'])
    print('PRODUCTION_BLOCKED_NO_REAL_CALIBRATED_THIRD_HARDWARE')

if __name__=='__main__':main()