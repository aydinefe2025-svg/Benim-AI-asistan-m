"""Reconcile two previously published *derived* Graz 5-cell evidence records.

No raw physical signal is reprocessed. The source is a reproducible, byte-pinned
snapshot of previously run genuine-publisher GitHub CI. Scientific claim gating
must reject clock, physical capacity, phase and safety statements unsupported
by evidence. These are *not* cryptographic lab calibration certificates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

DERIVED_TIME_SHA='213035922be15c6765e40d4a90c38e123de5e4b27556254ec8b614f6889e03b3'
DERIVED_ID_SHA='f6042b555021ada6d37989279734e5c900522ec1a5e9ed9b90ce4f761ab13205'
SOURCE_ZIP_SHA='5627a1606b8e378de0e4e4ced99222509bcbbcb725d26da6e7a5fad34aa42fc7'
DOI='10.5281/zenodo.22079387'
ORIGINAL_BYTES=10825955
SP_ROWS=234021
ELECTRICAL_ROWS=1091337
CELLS=('01','02','03','04','05')
CLAIM_RESTRICTIONS={
 'cross_instrument_clock_synchronization':
   'Independent calibrated UTC/physical trigger capture correlated to BOTH original electrical and SP device streams',
 'same_controller_experiment_phase':
   'Authentic controller program, sample-level step IDs and independent cross-device stage mapping',
 'calibrated_current_in_amperes':
   'Original device Current-unit declaration and instrument current-channel traceable calibration',
 'calibrated_capacity_Ah':
   'Both calibrated current units and verified phase/time windows, measured capacity repeats and integration uncertainty',
 'calibrated_sensor_displacement_or_force':
   'Sensor range/offset certificates and independently measured applied force with traceable uncertainty',
 'causal_preload_effect':
   'Multiple randomized/controlled physical specimens per preload and identified confounders',
 'dynamic_impact_safety':
   'True dynamic impact experiments plus calibrated force and independent verification of battery safety endpoints',
 'finite_element_mesh_convergence':
   'Identifiable mechanical material/geometric inputs, quantified boundary conditions, 3+ mesh levels and independent check',
 'physical_production_release':
   'Independent laboratory evidence, stable calibration chain and applicable hardware certification; software simulation cannot certify this',
}

def build_claim_ledger(time_bytes:bytes, identity_bytes:bytes)->dict:
    if not (isinstance(time_bytes,bytes) and isinstance(identity_bytes,bytes)
            and 0<len(time_bytes)<2000000 and 0<len(identity_bytes)<2000000):
        raise ValueError('both derived source evidence files are required')
    if hashlib.sha256(time_bytes).hexdigest()!=DERIVED_TIME_SHA:
        raise ValueError('time source derived evidence bytes changed')
    if hashlib.sha256(identity_bytes).hexdigest()!=DERIVED_ID_SHA:
        raise ValueError('electrical event identity source evidence bytes changed')
    a=json.loads(time_bytes)
    b=json.loads(identity_bytes)
    if a.get('source_doi')!=DOI or b.get('publisher_original_doi')!=DOI or (
        a.get('official_source_sha256')!=SOURCE_ZIP_SHA or b.get('original_zip_sha256')!=SOURCE_ZIP_SHA
    ) or a.get('source_original_bytes')!=ORIGINAL_BYTES:
        raise ValueError('not the exact original source provenance')
    if (not a.get('original_archive_crc_pass') or not b.get('full_publisher_zip_crc_and_size_pass')
         or a.get('same_physical_source_folders')!=5 or b.get('physical_cell_folders')!=5
         or set(a.get('cells',{}))!=set(CELLS) or set(b.get('cells',{}))!=set(CELLS)):
        raise ValueError('source identity, byte size and physical cell coverage mismatch')
    if not (a.get('original_electrical_rows')==b.get('original_electrical_records')==ELECTRICAL_ROWS and
            a.get('original_sp_sensor_rows')==b.get('original_SP_records')==SP_ROWS):
        raise ValueError('independent source rows disagreement')
    t=a.get('per_tolerance_sp_rows_with_nearest_electrical_timestamp',{})
    if not (t.get('0.5')==182225 and t.get('1.0')==t.get('2.5')==204673
        and a.get('remaining_unmatched_2p5_s')==29348
        and t['2.5']+a['remaining_unmatched_2p5_s']==SP_ROWS):
        raise ValueError('source time-matching totals are inconsistent')
    shifts=b.get('row_identity_accounting_by_shift',{})
    swapped={}
    for shift, expected_changed, expected_matched in [('-3.0',204671,204671),('3.0',204666,204666)]:
        z=shifts.get(shift,{})
        if not(z.get('0_offset_matched_SP_rows')==204673 and
            z.get('matched_in_both_DIFFERENT_electrical_source_record_index')==expected_changed and
            z.get('matched_in_both_same_electrical_source_record_index')==0 and
            z.get('shifted_matched_SP_rows')==expected_matched):
            raise ValueError('original event identity counterfactual evidence not reconciled')
        swapped[shift]={'shift_is_counterfactual_not_measured_clock_error':True,
          'changed_electrical_event_ids_while_both_offsets_match':expected_changed,
          'unchanged_electrical_event_ids':0,
          'calibrated_clock_offset_inferred':False}
    g=a.get('guardrails',{})
    k=b.get('conclusion_limits',{})
    required_false=('independent_instrument_clock_calibration_verified',
      'electrical_charge_discharge_protocol_phase_verified',
      'sensor_absolute_force_calibration_verified',
      'calibrated_battery_capacity_or_soh_reconstructed',
      'causal_load_effect_proven','dynamic_impact_measured')
    if any(g.get(key) is not False for key in required_false) or any(value is not False for value in k.values()):
        raise ValueError('original source does not authorize physical release claims')
    if g.get('measured_field_false_match_rate') is not None or g.get('cross_source_cell_ids_never_joined') is not True:
        raise ValueError('source labeling or field-match-rate assertion unsupported')
    return {
      'goal_key':'graz-20261123-real-derived-proof-claim-boundary-v4',
      'original_source_doi':DOI,
      'original_archive_sha256':SOURCE_ZIP_SHA,
      'source_evidence_sha256':{'five_cell_alignment':DERIVED_TIME_SHA,'event_identity_counterfactual':DERIVED_ID_SHA},
      'original_derived_evidence_integrity_pass':True,
      'real_original_electrical_rows':ELECTRICAL_ROWS,
      'real_original_sensor_rows':SP_ROWS,
      'timestamp_proximity_within_half_second':182225,
      'timestamp_proximity_within_one_second':204673,
      'timestamps_unmatched_at_2p5_seconds':29348,
      'counterfactual_event_identity_ambiguity':swapped,
      'physical_original_cells':list(CELLS),
      'actual_independent_hardware_certificates':0,
      'scientific_claims':{key:{'verified':False,'missing_independent_evidence':explanation}
          for key,explanation in CLAIM_RESTRICTIONS.items()},
      'software_v4_third_reference':{'simulation_only':True,
          'hardware_trigger_real_certificate_exists':False},
      'physical_production_release_allowed':False,
      'not_measured_field_false_positive_rate':True,
      'source_provenance_note':'Byte-exact pinned DERIVED CI JSON; not new source reprocessing or hardware certification'
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument('five_cell_derived_json',type=Path)
    p.add_argument('counterfactual_event_id_json',type=Path)
    p.add_argument('output',type=Path)
    a=p.parse_args()
    d=build_claim_ledger(a.five_cell_derived_json.read_bytes(),a.counterfactual_event_id_json.read_bytes())
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(d,indent=2,sort_keys=True,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print('REAL_GRAZ_SOURCE_INTEGRITY_OK',d['real_original_electrical_rows'],d['real_original_sensor_rows'])
    print('UNMATCHED',d['timestamps_unmatched_at_2p5_seconds'],'ALL_REAL_PHYSICAL_RELEASE_CLAIMS_BLOCKED')
if __name__=='__main__':main()