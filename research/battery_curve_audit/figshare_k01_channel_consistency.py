"""Gated charge vs discharge interpretation of real Figshare K01 ET/AT capacity.

The nine paired observations are THREE physical source-labeled cells measured
at three temperatures, not nine independent samples. Negative mean is NOT
proof that both capacity measurement channels decline. The original author
reports mean of step21 charge and step22 discharge capacity. If those channel
changes have opposite signs, the source is mixed and an unqualified loss claim
is disallowed. This does not estimate measurement uncertainty or field FPR.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from pathlib import Path
from hashlib import sha256
import json
import sys

SOURCE_SCHEMA='cano.battery.figshare279.original-k01-3cell-3temp-et-at-capacity.v1'
IDS={47639005,47627092,47627089}
FIELDS=('et_charge_capacity_Ah','et_discharge_capacity_Ah',
        'at_charge_capacity_Ah','at_discharge_capacity_Ah',
        'et_capacity_Ah','at_capacity_Ah')


def _cap(value, name):
    if isinstance(value,bool):
        raise ValueError('REVIEW_REQUIRED: boolean capacity '+name)
    try:
        n=Decimal(str(value))
    except (ValueError,TypeError,InvalidOperation):
        raise ValueError('REVIEW_REQUIRED: invalid numeric capacity '+name) from None
    if not n.is_finite() or not Decimal('0.01')<n<Decimal('8'):
        raise ValueError('REVIEW_REQUIRED: invalid numerical range for capacity '+name)
    return n


def _pct(at,et):
    return 100*(at/et-1)


def review_source_profiles(original_receipt:dict)->dict:
    if not isinstance(original_receipt,dict) or original_receipt.get('schema')!=SOURCE_SCHEMA:
        raise ValueError('REVIEW_REQUIRED: original source schema')
    if original_receipt.get('source_doi')!='10.6084/m9.figshare.25975315':
        raise ValueError('REVIEW_REQUIRED: publisher source DOI')
    for flag in ('external_physical_cell_custody_authenticated','field_FPR_FNR_established',
                 'storage_only_aging_attribution_proven','commercial_release_allowed'):
        if original_receipt.get(flag) is not False:
            raise ValueError('REVIEW_REQUIRED: unsupported physical/field claim')
    cells=original_receipt.get('source_archives')
    if not isinstance(cells,list) or len(cells)!=3 or original_receipt.get('source_capacity_pair_count')!=9:
        raise ValueError('REVIEW_REQUIRED: original 3-cell source count')
    seen_ids=set();result=[]
    for cell in cells:
        fid=cell.get('publisher_file_id')
        if fid not in IDS or fid in seen_ids:
            raise ValueError('REVIEW_REQUIRED: missing/duplicate original source ID')
        seen_ids.add(fid)
        if cell.get('original_crc_verified') is not True or cell.get('publisher_md5_verified') is not True:
            raise ValueError('REVIEW_REQUIRED: source checksum validation incomplete')
        profiles=cell.get('source_profiles')
        if not isinstance(profiles,list) or len(profiles)!=3:
            raise ValueError('REVIEW_REQUIRED: require 3 original test temperatures')
        temps=set()
        for p in profiles:
            t=p.get('temperature_C')
            if type(t) is not int or t not in (10,23,45) or t in temps:
                raise ValueError('REVIEW_REQUIRED: missing or duplicated source temperature')
            temps.add(t)
            for key in ('source_sidecar_identity_matched',
                        'original_step21_and_step22_valid_both_phases',
                        'measurement_source_temperature_matched'):
                if p.get(key) is not True:
                    raise ValueError('REVIEW_REQUIRED: source measurement validity gate')
            if p.get('physical_identity_independently_authenticated') is not False or p.get('storage_only_aging_attribution_proved') is not False:
                raise ValueError('REVIEW_REQUIRED: unsupported source physical claim')
            d={name:_cap(p.get(name),name) for name in FIELDS}
            for ph in ('et','at'):
                expected=(d[f'{ph}_charge_capacity_Ah']+d[f'{ph}_discharge_capacity_Ah'])/2
                if abs(expected-d[f'{ph}_capacity_Ah'])>Decimal('0.0000011'):
                    raise ValueError('REVIEW_REQUIRED: recorded mean disagrees with charge/discharge original channels')
            charge=_pct(d['at_charge_capacity_Ah'],d['et_charge_capacity_Ah'])
            discharge=_pct(d['at_discharge_capacity_Ah'],d['et_discharge_capacity_Ah'])
            mean=_pct(d['at_capacity_Ah'],d['et_capacity_Ah'])
            supplied=p.get('et_to_at_change_percent')
            if not isinstance(supplied,(int,float,Decimal)) or isinstance(supplied,bool) or abs(mean-Decimal(str(supplied)))>Decimal('0.0002'):
                raise ValueError('REVIEW_REQUIRED: recorded source mean percent inconsistent')
            if charge<0 and discharge<0:
                direction='BOTH_CHANNELS_DECLINE_OBSERVED'
            elif charge>0 and discharge>0:
                direction='BOTH_CHANNELS_INCREASE_OBSERVED'
            elif charge*discharge<0:
                direction=('MIXED_SIGN_MEAN_LOSS_NOT_BOTH_CHANNEL_LOSS'
                           if mean<0 else 'MIXED_SIGN_REVIEW_REQUIRED')
            else:
                direction='ZERO_DIRECTION_CHANNEL_REVIEW_REQUIRED'
            result.append({
                'source_archive_id':fid,'temperature_C':t,
                'source_mean_delta_percent':float(round(mean,4)),
                'charge_channel_delta_percent':float(round(charge,4)),
                'discharge_channel_delta_percent':float(round(discharge,4)),
                'absolute_charge_discharge_direction_gap_pp':float(round(abs(charge-discharge),4)),
                'decision':direction,
                'unqualified_aging_loss_established':False,
                'field_FPR_FNR_established':False,
            })
    if seen_ids!=IDS or len(result)!=9:
        raise ValueError('REVIEW_REQUIRED: original 9-cell-temperature profiles incomplete')
    result.sort(key=lambda x:(x['source_archive_id'],x['temperature_C']))
    return {
        'schema':'cano.battery.figshare279.k01-original-channel-consistency.v1',
        'source_doi':'10.6084/m9.figshare.25975315',
        'source_groups':3,'source_temperature_pairs':9,
        'mean_negative_pairs':sum(x['source_mean_delta_percent']<0 for x in result),
        'both_charge_and_discharge_negative_pairs':sum(x['decision']=='BOTH_CHANNELS_DECLINE_OBSERVED' for x in result),
        'mixed_sign_pairs':sum(x['decision'].startswith('MIXED_SIGN') for x in result),
        'max_channel_change_gap_pp':max(x['absolute_charge_discharge_direction_gap_pp'] for x in result),
        'comparisons':result,
        'unqualified_9_of_9_aging_loss_claim_allowed':False,
        'technical_replication_not_independent_cell':True,
        'storage_only_aging_attribution_proven':False,
        'physical_identity_independently_authenticated':False,
        'field_FPR_FNR_established':False,
        'production_release_allowed':False,
        'decision':'ORIGINAL_CHANNEL_SIGN_DISCORDANCE_REQUIRES_SEPARATE_CHARGE_DISCHARGE_REPORTING',
    }


def run(offline_dir:Path|None=None):
    from research.battery_curve_audit.figshare_k01_three_temperatures import run as original_run
    source=original_run(offline_dir)
    output=review_source_profiles(source)
    output['original_source_receipt_sha256']=sha256((json.dumps(source,sort_keys=True)+'\n').encode()).hexdigest()
    output['original_source_rows_processed']=source['original_timestamp_voltage_current_rows_processed']
    output['original_csv_files_processed']=source['original_csv_files_processed']
    output['original_archive_sha256_by_id']=[{'publisher_file_id':x['publisher_file_id'],'original_sha256':x['original_sha256']} for x in source['source_archives']]
    output['original_archive_md5_crc_verified']=True
    return output


def main(argv=None):
    args=list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) not in (1,3) or (len(args)==3 and args[1]!='--offline-originals'):
            raise ValueError('usage: python -m research.battery_curve_audit.figshare_k01_channel_consistency OUT.json [--offline-originals DIR]')
        path=Path(args[0])
        if path.exists() or not path.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: output exists or parent is missing')
        offline=Path(args[2]) if len(args)==3 else None
        out=run(offline)
        with path.open('x',encoding='utf-8') as f:
            json.dump(out,f,sort_keys=True,indent=2);f.write('\n')
        print('REAL_ORIGINAL_CHANNEL_GUARD',json.dumps({
            'source_rows':out['original_source_rows_processed'],
            'mean_decreases':out['mean_negative_pairs'],
            'both_channels_decrease':out['both_charge_and_discharge_negative_pairs'],
            'mixed_sign':out['mixed_sign_pairs']},sort_keys=True))
        return 0
    except (ValueError,OSError,TypeError,KeyError,json.JSONDecodeError) as exc:
        print('SOURCE_REVIEW_REQUIRED:',str(exc)[:180],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())