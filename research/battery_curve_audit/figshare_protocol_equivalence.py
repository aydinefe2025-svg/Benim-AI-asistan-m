"""Conservatively cross-check original Figshare 25975315 source protocol coding.

Supports strict paper-documented type/TP/cell meanings and source-sidecar testpoint.
No lab custody, instrument calibration, phase sync, or field accuracy certification.
"""
from __future__ import annotations
import csv
from datetime import datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import sys
from zipfile import ZipFile

ARCHIVE = re.compile(r'^TP_([kz])(\d{1,2})_(\d{1,2})$')
SIDECAR_TP = re.compile(r'^(?:TP[_ -]?)?([kz])[_ -]?(\d{1,2})(?:[_ -](\d{1,2}))?$', re.I)
DATE_FORMATS = ('%Y-%m-%dT%H:%M:%S.%f','%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S',
                '%d.%m.%Y %H:%M:%S','%d/%m/%Y %H:%M:%S','%Y-%m-%d',
                '%d.%m.%Y')


def _strict_int(value:object)->int:
    raw=str(value or '').strip()
    if not re.fullmatch(r'\d{1,3}',raw):
        raise ValueError('SOURCE_REVIEW_REQUIRED: nonpositive/noninteger source protocol number')
    out=int(raw)
    if not 1<=out<=999:
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source protocol integer')
    return out


def compare_protocol_identifiers(archive_stem:str, overview_row:dict,
                                 sidecar_testpoint:str|None)->dict:
    """Compare declared type, testpoint and cell; forbid fuzzy substring matching."""
    if not isinstance(archive_stem,str) or not (m:=ARCHIVE.fullmatch(archive_stem)):
        raise ValueError('SOURCE_REVIEW_REQUIRED: bad source archive stem')
    kind,number,cell=m.group(1),int(m.group(2)),int(m.group(3))
    rowtype=str(overview_row.get('type','')).strip().casefold()
    rowtp=_strict_int(overview_row.get('tp'))
    rowcell=_strict_int(overview_row.get('cell'))
    matches=rowtype==kind and rowtp==number and rowcell==cell
    sidecar_match=None
    sidecar_shape='missing'
    if sidecar_testpoint is not None and str(sidecar_testpoint).strip():
        r=SIDECAR_TP.fullmatch(str(sidecar_testpoint).strip())
        if r is None:
            sidecar_shape='unrecognized'
        else:
            sidecar_shape='type_tp_cell' if r.group(3) else 'type_tp'
            sidecar_match=(r.group(1).lower()==kind and int(r.group(2))==number
                           and (r.group(3) is None or int(r.group(3))==cell))
    if not matches:
        decision='OVERVIEW_PROTOCOL_CONFLICT_REVIEW_REQUIRED'
    elif sidecar_match is False:
        decision='SIDECAR_TESTPOINT_CONFLICT_REVIEW_REQUIRED'
    elif sidecar_match is None:
        decision='SIDECAR_TESTPOINT_FORMAT_REVIEW_REQUIRED'
    else:
        decision='PUBLISHER_PROTOCOL_RECORDS_EQUIVALENT_NOT_PHYSICAL_CERTIFICATION'
    return {'overview_filename_type_tp_cell_match':matches,
            'sidecar_testpoint_equivalent':sidecar_match,
            'sidecar_testpoint_shape':sidecar_shape,
            'source_paper_type_code':kind,
            'decision':decision,
            'physical_conditions_independently_verified':False}


def _parse_date(raw:object)->datetime|None:
    text=str(raw or '').strip()
    if not text or len(text)>80:return None
    for f in DATE_FORMATS:
        try:return datetime.strptime(text,f)
        except ValueError:pass
    try:
        result=datetime.fromisoformat(text.replace('Z','+00:00'))
        return result
    except (ValueError,TypeError):
        return None


def inspect_sidecar_setup(fields:dict)->dict:
    """Report only source metadata completeness and anonymous categorical checks."""
    def present(key):
        v=fields.get(key)
        return isinstance(v,str) and 0<len(v.strip())<=250 and '\x00' not in v
    date=_parse_date(fields.get('measurement_start_date'))
    checks={'device_record_present':present('measurement_device_used'),
            'channel_record_present':present('test_channel'),
            'start_time_record_present':present('measurement_start_date'),
            'start_time_record_parseable':date is not None,
            'climate_chamber_record_present':present('climate_chamber_used'),
            'climate_chamber_setpoint_record_present':present('climate_chamber_temperature_setpoint'),
            'position_record_present':present('position_within_climate_chamber'),
            'device_calibration_independently_verified':False,
            'experiment_start_clock_independently_synchronized':False}
    checks['all_required_source_setup_labels_present']=all(checks[k] for k in (
        'device_record_present','channel_record_present','start_time_record_parseable'))
    return checks


def crosscheck_publisher_row(archive_stem:str, overview_row:dict,fields:dict)->dict:
    protocol=compare_protocol_identifiers(archive_stem,overview_row,fields.get('testpoint'))
    setup=inspect_sidecar_setup(fields)
    return {**protocol,**setup,
            'publisher_record_protocol_consistent':(protocol['overview_filename_type_tp_cell_match']
               and protocol['sidecar_testpoint_equivalent'] is True),
            'physical_cell_independently_authenticated':False,
            'field_acceptance':'NOT_ESTABLISHED',
            'production_release_allowed':False}


def original_protocol_overview(raw:bytes)->dict:
    """Read protocol row fields after upstream exact publisher MD5 check."""
    if not isinstance(raw,bytes) or not 0<len(raw)<=50000:
        raise ValueError('SOURCE_REVIEW_REQUIRED: publisher overview byte count')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig'),newline=''))
    if not reader.fieldnames or len(set(x.strip() for x in reader.fieldnames))!=len(reader.fieldnames):
        raise ValueError('SOURCE_REVIEW_REQUIRED: overview header')
    columns={x.strip().casefold():x for x in reader.fieldnames}
    if not {'stage','serial','type','tp','cell'}.issubset(columns):
        raise ValueError('SOURCE_REVIEW_REQUIRED: publisher protocol columns absent')
    from research.battery_curve_audit.figshare_identity_provenance import _stage
    result={}
    for row in reader:
        if None in row:raise ValueError('SOURCE_REVIEW_REQUIRED: ragged overview')
        key=(_stage(row[columns['stage']]),str(row[columns['serial']] or '').strip())
        if key in result or not key[1]:raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate protocol key')
        result[key]={c:str(row[columns[c]] or '') for c in ('type','tp','cell')}
        if len(result)>1000:raise ValueError('SOURCE_REVIEW_REQUIRED: overview row cap')
    if len(result)!=279:raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected publisher row count')
    return result


def run()->dict:
    """Only publisher-original 30KB CSV and three MD5/CRC-pinned ~7MB ZIPs."""
    from research.battery_curve_audit.figshare_three_archive_probe import (
        URL,MAX_META_BYTES,MAX_SOURCE_BYTES,fetch_bounded,inspect_zip,validate_source_meta)
    from research.battery_curve_audit.figshare25975315_small_csv import (
        CSV_FILE_ID,MAX_ORIGINAL_CSV_BYTES,locate_publisher_file,inspect_original_csv)
    from research.battery_curve_audit.figshare_identity_provenance import (
        read_overview,verify_cell_directory,summarize_meta_sidecar,reconcile_records)
    article_bytes=fetch_bounded(URL,MAX_META_BYTES)
    article=json.loads(article_bytes)
    pins=validate_source_meta(article)
    overview_pin=locate_publisher_file(article)
    original_csv=fetch_bounded(f'https://ndownloader.figshare.com/files/{CSV_FILE_ID}',MAX_ORIGINAL_CSV_BYTES)
    overview_receipt=inspect_original_csv(original_csv,overview_pin)
    identity=read_overview(original_csv)
    protocol=original_protocol_overview(original_csv)
    if set(identity)!=set(protocol):raise ValueError('SOURCE_REVIEW_REQUIRED: overview key disagreement')
    observations=[]
    for pub in pins:
        data=fetch_bounded('https://ndownloader.figshare.com/files/'+str(pub['id']),MAX_SOURCE_BYTES)
        verified=inspect_zip(data,pub)
        with ZipFile(io.BytesIO(data)) as z:
            loc=verify_cell_directory(z,pub['name'][:-4])
        sidecar=summarize_meta_sidecar(loc.pop('sidecar_bytes'))
        joined=reconcile_records(loc,identity,sidecar)
        if not joined['source_record_identity_cross_linked'] or joined['stage'] is None:
            raise ValueError('SOURCE_REVIEW_REQUIRED: original identity not uniquely joined')
        key=(joined['stage'],loc['serial'])
        check=crosscheck_publisher_row(pub['name'][:-4],protocol[key],sidecar['parsed_fields'])
        observations.append({'publisher_original_file_id':pub['id'],
          'source_archive_sha256':verified['original_zip_sha256'],
          'source_meta_sha256':loc['sidecar_sha256'],
          'publisher_source_identity_record_linked':True,
          **check})
    # No raw instrument/channel identities, internal serials, dates or signal rows in receipt.
    return {'schema':'cano.battery.figshare25975315.original-3-type-tp-cell-instrument-crosswalk.v1',
      'article_id':25975315,'publisher_overview_sha256':overview_receipt['original_file_sha256'],
      'original_overview_row_count':len(protocol),
      'source_files_verified_md5_crc':len(observations),
      'original_author_paper_protocol_codes_verified':False, # paper context is not a human signature
      'source_measurement_records':observations,
      'type_tp_cell_agreed_count':sum(x['overview_filename_type_tp_cell_match'] for x in observations),
      'sidecar_testpoint_equivalent_count':sum(x['sidecar_testpoint_equivalent'] is True for x in observations),
      'sidecar_testpoint_unrecognized_count':sum(x['sidecar_testpoint_equivalent'] is None for x in observations),
      'measurement_setup_label_complete_count':sum(x['all_required_source_setup_labels_present'] for x in observations),
      'physical_cell_independently_authenticated':False,
      'measuring_device_calibration_independently_verified':False,
      'measurement_timebase_independently_calibrated':False,
      'independent_lab_institution_authenticated':False,
      'field_FPR_FNR_established':False,
      'field_acceptance':'NOT_ESTABLISHED',
      'production_release_allowed':False,
      'decision':'PUBLISHER_SOURCE_PROTOCOL_METADATA_CHECK_RESEARCH_ONLY'}


def main(argv=None)->int:
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        print('usage: python -m research.battery_curve_audit.figshare_protocol_equivalence output.json',file=sys.stderr);return 2
    try:
        output=Path(args[0]);
        if output.exists() or not output.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: output exists or parent absent')
        data=run()
        with output.open('x',encoding='utf8') as f:json.dump(data,f,indent=2,sort_keys=True);f.write('\n')
        print('PUBLISHER_ORIGINAL_PROTOCOL',data['type_tp_cell_agreed_count'],
              'sidecar_tp_equiv',data['sidecar_testpoint_equivalent_count'],
              'setup_records',data['measurement_setup_label_complete_count'])
        return 0
    except (ValueError, OSError, UnicodeError, KeyError,TypeError, csv.Error) as err:
        print('SOURCE_REVIEW_REQUIRED:',str(err)[:180],file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())