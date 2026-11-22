"""Conservative *conditional* catalog accuracy envelopes for original battery receipts.

This never calibrates a physical instrument. It never claims a statistically
valid 95% confidence interval or independently measured error. The model-family
scenarios may not apply to the original channel/range of a 2021-2022 tester.

Source numeric receipts were previously verified against original publisher ZIPs
in Github real-source CI and independently read from canonical Library. Inputs
contain the minimal stable derived observations, not source waveform replays.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

EXPECTED_SOURCE_SHA256 = {
    'bf53056fcf6138729397315164c86d7419765d99677607e413531bfd20363f87',
    '0188c483077d10af351ee6df773a083ce09f1767a396456da95becf7c9db4eaa',
}
EXPECTED_CELLS = {'TP_k01_04','TP_k01_05','TP_k04_05','TP_k04_06'}
EXPECTED_TEMPS = {10,23,45}


def finite_pos(value, field):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
        raise ValueError('SOURCE_REVIEW_REQUIRED: '+field)
    return float(value)


def validate(ledger, assumptions):
    if ledger.get('schema')!='battery.instrument-family-conditional-measurement-envelope.input.v1':
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong source schema')
    if assumptions.get('schema')!='battery.instrument-family-conditional-measurement-envelope.assumptions.v1':
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong scenario schema')
    if assumptions.get('not_a_calibration_certificate') is not True or ledger.get('original_sensor_calibration_certificates_obtained') is not False:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source calibration claims')
    if ledger.get('device_family_scenarios_not_serial_specific_certificates') is not True:
        raise ValueError('SOURCE_REVIEW_REQUIRED: scenario vs certification confused')
    if ledger.get('physically_independent_source_cell_count')!=4 or ledger.get('source_T10_phase_CSV_count')!=8 or ledger.get('source_3_temperature_pulse_CSV_count')!=24:
        raise ValueError('SOURCE_REVIEW_REQUIRED: source denominator mismatch')
    rs=ledger.get('source_evidence_refs',[])
    if len(rs)!=2 or {x.get('sha256') for x in rs}!=EXPECTED_SOURCE_SHA256:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original measured source receipts not pinned')
    assert isinstance(ledger['source_cells'],list)
    cells=ledger['source_cells'];pulses=ledger['pulse_condition_pairs']
    if len(cells)!=4 or {x.get('source_cell') for x in cells}!=EXPECTED_CELLS:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original source cell identity collision')
    if len(pulses)!=12 or {(x.get('source_cell'),x.get('temp_setpoint_C')) for x in pulses}!={(c,t) for c in EXPECTED_CELLS for t in EXPECTED_TEMPS}:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original pulse condition denominator mismatch')
    if len(assumptions.get('sources',[]))<3 or not all(x.get('source_url','').startswith('https://') for x in assumptions['sources']):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing dated family source')
    v=assumptions['uniform_voltage_error_scenario']
    finite_pos(v['single_voltage_reading_max_abs_mV'],'voltage scenario')
    for c in cells:
        if c.get('source_ET_AT_instrument_channel_chamber_stable') is not True:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source device continuity not verified')
        if len(c.get('source_original_zip_sha256',''))!=64:
            raise ValueError('SOURCE_REVIEW_REQUIRED: missing original ZIP hash')
        finite_pos(c['duration_ET_s'],'ET discharge duration')
        finite_pos(c['duration_AT_s'],'AT discharge duration')
        finite_pos(c['discharge_delta_mAh'],'discharge delta must be positive for exact four known cells')
        family=c.get('family')
        if family not in assumptions['family_current_accuracy_scenarios']:
            raise ValueError('SOURCE_REVIEW_REQUIRED: unknown family')
        a=assumptions['family_current_accuracy_scenarios'][family]
        finite_pos(a['assumed_abs_current_mA_each_channel'],'current accuracy scenario')
        if isinstance(a['parallel_channels'],bool) or a['parallel_channels'] not in (1,2):
            raise ValueError('SOURCE_REVIEW_REQUIRED: physical current channel count')
        if (family.startswith('CTS_') and a['parallel_channels']!=2) or (family.startswith('XCTS_') and a['parallel_channels']!=1):
            raise ValueError('SOURCE_REVIEW_REQUIRED: source channel mismatch')
    for p in pulses:
        finite_pos(abs(p['discharge_pulse_current_ET_A']),'ET pulse current')
        finite_pos(abs(p['discharge_pulse_current_AT_A']),'AT pulse current')
        if not all(math.isfinite(p[k]) for k in ('corrected_DCiR_AT_minus_ET_mOhm','discharge_pulse_current_ET_A','discharge_pulse_current_AT_A')):
            raise ValueError('SOURCE_REVIEW_REQUIRED: nonfinite pulse')
        if p['discharge_pulse_current_ET_A']>=0 or p['discharge_pulse_current_AT_A']>=0:
            raise ValueError('SOURCE_REVIEW_REQUIRED: expected source discharge pulse')


def run(ledger, assumptions):
    validate(ledger,assumptions)
    a=assumptions['family_current_accuracy_scenarios'];v=assumptions['uniform_voltage_error_scenario']['single_voltage_reading_max_abs_mV']
    cells=[];caps={}
    for c in sorted(ledger['source_cells'],key=lambda x:x['source_cell']):
        r=a[c['family']]
        per_pair_mA=r['assumed_abs_current_mA_each_channel']*r['parallel_channels']
        # For constant bounded current reading error in ET and AT, worst case
        # |error in (AT-ET) capacity| <= E_AT*T_AT + E_ET*T_ET.
        bound_mAh=(per_pair_mA*(c['duration_AT_s']+c['duration_ET_s']))/3600
        observed=c['discharge_delta_mAh'];id=c['source_cell']
        caps[id]=dict(source_cell=id,family=c['family'],
            original_zip_sha256=c['source_original_zip_sha256'],
            original_discharge_ET_duration_s=c['duration_ET_s'],
            original_discharge_AT_duration_s=c['duration_AT_s'],
            observed_AT_minus_ET_discharge_capacity_mAh=round(observed,6),
            hypothetical_catalog_current_accuracy_mA_per_channel=r['assumed_abs_current_mA_each_channel'],
            hypothetical_parallel_channels=r['parallel_channels'],
            hypothetical_max_ET_AT_current_error_only_mAh=round(bound_mAh,6),
            observed_exceeds_hypothetical_error_only_bound=bool(observed>bound_mAh),
            ratio_observed_to_hypothetical_current_only_bound=round(observed/bound_mAh,4),
            inference='CURRENT_ERROR_ALONE_EXCEEDS_MODELED_FAMILY_BOUND_NOT_A_CAUSAL_PROOF' if observed>bound_mAh else 'CURRENT_ERROR_ONLY_NOT_EXCLUDED_BY_BROAD_FAMILY_SCENARIO')
        cells.append(caps[id])
    pulses=[]
    for p in sorted(ledger['pulse_condition_pairs'],key=lambda x:(x['source_cell'],x['temp_setpoint_C'])):
        # ±v mV independently for pre/rest and 10s voltage in each of ET, AT:
        # a simple 4-voltage-sample worst-case max variation in delta-R, not a
        # statistical CI, not OCV correction accuracy, and ignoring I uncertainty.
        voltage_only_bound_mOhm=2*v/abs(p['discharge_pulse_current_ET_A'])+2*v/abs(p['discharge_pulse_current_AT_A'])
        delta=p['corrected_DCiR_AT_minus_ET_mOhm']
        pulses.append(dict(source_cell=p['source_cell'],temperature_setpoint_C=p['temp_setpoint_C'],
            measured_surface_temperature_NOT_assumed_equal_setpoint=True,
            observed_corrected_DCiR_AT_minus_ET_mOhm=round(delta,6),
            hypothetical_four_voltage_reading_deltaR_max_mOhm=round(voltage_only_bound_mOhm,6),
            magnitude_below_hypothetical_voltage_only_scenario=bool(abs(delta)<voltage_only_bound_mOhm),
            ratio_observed_magnitude_to_voltage_scenario=round(abs(delta)/voltage_only_bound_mOhm,4)))
    out=dict(schema='battery.instrument-family-conditional-measurement-envelope.result.v1',
        goal_key=ledger['goal_key'],
        input_original_source_evidence_refs=ledger['source_evidence_refs'],
        source_cell_count=4,condition_pair_count=12,
        capacity_current_only_scenarios=cells,
        dcir_voltage_only_scenarios=pulses,
        cells_exceeding_current_only_catalog_scenario=sum(x['observed_exceeds_hypothetical_error_only_bound'] for x in cells),
        dcir_condition_pairs_below_voltage_only_hypothetical_scenario=sum(x['magnitude_below_hypothetical_voltage_only_scenario'] for x in pulses),
        published_specs_are_serial_number_specific_calibration=False,
        source_2021_2022_instrument_calibration_obtained=False,
        control_termination_voltage_time_uncertainty_quantified=False,
        uncertainty_95pct_confidence_interval_established=False,
        temperature_causal_adjustment_established=False,
        externally_verified_cell_custody=False,
        physical_aging_causality_established=False,
        population_279_cell_fpr_fnr_established=False,
        commercial_production_release_allowed=False,
        decision='RESEARCH_ONLY_EXTERNAL_CALIBRATION_AND_REPEATED_LAB_DATA_REQUIRED',
        explanation='Illustrative historical device-family error-only upper-bound scenarios. Cannot certify actual 2021/2022 tester accuracy, independently observed bias, controller stopping-point changes, true cell capacity recovery, aging causality, or statistical significance. Common-mode error covariance and thermal/OCV errors are not modeled.')
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('verified_source_derived_minimal_ledger',type=Path)
    parser.add_argument('instrument_family_assumptions',type=Path)
    parser.add_argument('output_json',type=Path)
    x=parser.parse_args()
    result=run(json.loads(x.verified_source_derived_minimal_ledger.read_text()),
               json.loads(x.instrument_family_assumptions.read_text()))
    x.output_json.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print('ORIGINAL_SOURCE_RECEIPT_CATALOG_SCENARIO',result['source_cell_count'],
        result['condition_pair_count'],result['cells_exceeding_current_only_catalog_scenario'],
        result['dcir_condition_pairs_below_voltage_only_hypothetical_scenario'])


if __name__=='__main__':
    main()