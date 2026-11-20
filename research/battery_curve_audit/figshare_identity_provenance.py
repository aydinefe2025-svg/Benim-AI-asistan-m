"""Verify original Figshare 279 overview-to-3 ZIP sidecar identities.

Evidence gates: bytes match publisher MD5, ZIP CRC and paths; sidecar values are
never uploaded. A matching publisher record is NOT physical identity attestation.
"""
from __future__ import annotations
import csv
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import sys
import unicodedata
from zipfile import ZipFile

MAX_CSV_BYTES = 50_000
MAX_META_BYTES_PER_FILE = 50_000
MAX_OVERVIEW_ROWS = 1_000


def _stage(value: object) -> str:
    value = str(value or '').strip().casefold()
    m = re.fullmatch(r'(?:stage[_ -]*)?([12])', value)
    if not m:
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid or unknown experiment stage')
    return m.group(1)


def _identity(value: object) -> str:
    return unicodedata.normalize('NFKC', str(value or '')).strip().casefold()


def read_overview(raw: bytes) -> dict:
    """Authoritative *publisher-record* identity uses composite stage+serial."""
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_CSV_BYTES:
        raise ValueError('SOURCE_REVIEW_REQUIRED: overview byte budget')
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid overview UTF8') from exc
    if '\x00' in content:
        raise ValueError('SOURCE_REVIEW_REQUIRED: binary overview')
    reader = csv.DictReader(io.StringIO(content, newline=''))
    if not reader.fieldnames or len(reader.fieldnames) > 100:
        raise ValueError('SOURCE_REVIEW_REQUIRED: malformed overview headers')
    fields = [name.strip().casefold() for name in reader.fieldnames]
    if len(set(fields)) != len(fields):
        raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate overview column')
    required = {'stage','serial','lab','serial_internal'}
    if not required.issubset(fields):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing authoritative overview columns')
    orig = {x.strip().casefold(): x for x in reader.fieldnames}
    out = {}
    for index, row in enumerate(reader,1):
        if index > MAX_OVERVIEW_ROWS or None in row:
            raise ValueError('SOURCE_REVIEW_REQUIRED: inconsistent overview CSV')
        serial = str(row[orig['serial']] or '').strip()
        internal = str(row[orig['serial_internal']] or '').strip()
        lab = str(row[orig['lab']] or '').strip()
        if not serial or not internal or not lab:
            raise ValueError('SOURCE_REVIEW_REQUIRED: blank overview cell identity')
        key = (_stage(row[orig['stage']]), serial)
        if key in out:
            raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate composite stage+serial')
        out[key] = {
            'stage':key[0], 'serial':serial, 'serial_internal':internal, 'lab':lab,
            'tp':str(row[orig['tp']] or '').strip() if 'tp' in orig else None,
            'cell':str(row[orig['cell']] or '').strip() if 'cell' in orig else None}
    if not out:
        raise ValueError('SOURCE_REVIEW_REQUIRED: overview empty')
    return out


def verify_cell_directory(z:ZipFile, archive_serial:str) -> dict:
    """Discover exactly one first ET_T23 recording + metadata within a stage path."""
    if not re.fullmatch(r'TP_[kz]\d{2}_\d{2}', archive_serial):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid expected archive serial')
    names=z.namelist()
    if len(set(names)) != len(names):
        raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate ZIP names')
    filename=f'{archive_serial}_01_ET_T23.csv'
    matches=[name for name in names if PurePosixPath(name).name == filename]
    if len(matches) != 1:
        raise ValueError('SOURCE_REVIEW_REQUIRED: ambiguous or absent original source CSV')
    path=PurePosixPath(matches[0])
    if path.is_absolute() or '\\' in matches[0] or '..' in path.parts or any(not x for x in path.parts):
        raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe source path')
    stage_paths=[p for p in path.parts[:-1] if re.fullmatch(r'Stage_[12]',p)]
    if len(stage_paths)>1:
        raise ValueError('SOURCE_REVIEW_REQUIRED: ambiguous source stage directories')
    for directory in path.parts[:-1]:
        if re.fullmatch(r'TP_[kz]\d{2}_\d{2}',directory) and directory!=archive_serial:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source parent directory identity mismatch')
    stage=_stage(stage_paths[0]) if stage_paths else None
    paired=str(path)[:-4]+'_meta.txt'
    if paired not in names:
        raise ValueError('SOURCE_REVIEW_REQUIRED: paired source metadata missing')
    if z.getinfo(paired).file_size>MAX_META_BYTES_PER_FILE:
        raise ValueError('SOURCE_REVIEW_REQUIRED: sidecar too large')
    sidecar=z.read(paired)
    if len(sidecar)>MAX_META_BYTES_PER_FILE:
        raise ValueError('SOURCE_REVIEW_REQUIRED: sidecar read budget')
    return {'stage':stage,'stage_origin':'source_path' if stage is not None else 'unavailable',
            'path_depth':len(path.parts),'serial':archive_serial,
            'csv_name_suffix':filename,'sidecar_name_suffix':PurePosixPath(paired).name,
            'sidecar_sha256':sha256(sidecar).hexdigest(),'sidecar_bytes':sidecar}


def _key_name(raw: str) -> str:
    key=unicodedata.normalize('NFKC',raw).casefold().strip()
    key=re.sub(r'[^a-z0-9_]+','_',key).strip('_')
    return key


def summarize_meta_sidecar(raw:bytes) -> dict:
    """Parse labeled source-sidecar data privately; return values only internally."""
    if not isinstance(raw,bytes) or not 0 < len(raw)<=MAX_META_BYTES_PER_FILE:
        raise ValueError('SOURCE_REVIEW_REQUIRED: sidecar byte budget')
    try:
        content=raw.decode('utf-8-sig')
        encoding='utf8'
    except UnicodeDecodeError:
        content=raw.decode('iso-8859-1')
        encoding='latin1'
    if '\x00' in content or any(ord(c)<32 and c not in '\n\t\r' for c in content):
        raise ValueError('SOURCE_REVIEW_REQUIRED: sidecar control byte')
    parsed={}
    keys=[]
    lines=content.splitlines()
    if len(lines)>1000:
        raise ValueError('SOURCE_REVIEW_REQUIRED: sidecar line count')
    for line in lines:
        m=re.match(r'^\s*([^:=\t]{1,65})\s*[:=\t]\s*(.*?)\s*$',line)
        if not m or not m.group(2):
            continue
        key=_key_name(m.group(1))
        if not key or len(key)>64:
            continue
        if key in parsed:
            raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate sidecar field')
        parsed[key]=m.group(2).strip()
        keys.append(key)
    return {'encoding':encoding,'line_count':len(lines),
            'parsed_fields':parsed,'field_keys':sorted(keys)[:60],
            'format':'labeled_lines' if parsed else 'unrecognized'}


def _first(parsed: dict, keys:tuple[str,...]):
    for key in keys:
        if key in parsed:
            return parsed[key]
    return None


def _norm_testpoint(value:object) -> str:
    """Normalize the published TP prefix only (never a fuzzy or numeric join)."""
    v=_identity(value)
    return v[3:] if v.startswith('tp_') else v


def reconcile_records(location:dict, overview:dict, meta:dict) -> dict:
    """Join separate *publisher* records; NEVER assert physical/human custody."""
    stage=location['stage']
    stage_origin=location.get('stage_origin','source_path' if stage is not None else 'unavailable')
    fields=meta['parsed_fields']
    internal=_first(fields,('serial_internal','internal_serial','internal_cell_serial','cell_serial_internal'))
    lab=_first(fields,('lab','laboratory','lab_id','laboratory_identifier'))
    tp=_first(fields,('tp','testpoint','test_point','testpoint_identifier'))
    # Aggregate-only diagnosis of source formats. No original identifiers leak.
    all_rows=list(overview.values())
    serial_pred=lambda row:_identity(row['serial'])==_identity(location['serial'])
    internal_pred=lambda row:internal is not None and _identity(row['serial_internal'])==_identity(internal)
    lab_pred=lambda row:lab is not None and _identity(row['lab'])==_identity(lab)
    tp_pred=lambda row:tp is not None and row['tp'] is not None and _norm_testpoint(row['tp'])==_norm_testpoint(tp)
    evidence_counts={
        'overview_same_archive_serial':sum(serial_pred(row) for row in all_rows),
        'overview_matching_internal_serial':sum(internal_pred(row) for row in all_rows),
        'overview_matching_lab':sum(lab_pred(row) for row in all_rows),
        'overview_matching_testpoint':sum(tp_pred(row) for row in all_rows),
        'overview_same_archive_serial_internal_and_lab':sum(serial_pred(row) and internal_pred(row) and lab_pred(row) for row in all_rows),
        'overview_same_archive_serial_internal_lab_and_testpoint':sum(serial_pred(row) and internal_pred(row) and lab_pred(row) and tp_pred(row) for row in all_rows),
    }
    out={'stage':stage,'stage_origin':stage_origin,
         'overview_composite_key_found':False,
         'source_record_identity_cross_linked':False,
         'diagnostic_matching_row_counts':evidence_counts,
         'sidecar_format':meta['format'],
         'sidecar_label_keys':meta['field_keys'],
         'sidecar_lab_matches_overview':False,
         'sidecar_internal_id_matches_overview':False,
         'sidecar_testpoint_matches_overview':False,
         'sidecar_lab_field_recognized':lab is not None,
         'sidecar_internal_id_field_recognized':internal is not None,
         'sidecar_testpoint_field_recognized':tp is not None,
         'physical_identity_authenticated':False,
         'laboratory_institution_independently_authenticated':False}

    if stage is None:
        explicit_stage=_first(fields,('stage','experiment_stage','measurement_stage'))
        if explicit_stage is not None:
            stage=_stage(explicit_stage)
            stage_origin='explicit_sidecar_field'
        elif internal is not None and lab is not None:
            # Filename serial alone collides across Stage_1 and Stage_2. A
            # cross-record stage join needs independent label values from the
            # paired original sidecar, not guessed stage from folder or paper.
            same_serial=[row for row in overview.values()
                         if _identity(row['serial'])==_identity(location['serial'])]
            candidates=[row for row in same_serial
                        if _identity(row['serial_internal'])==_identity(internal)
                        and _identity(row['lab'])==_identity(lab)]
            if len(candidates)==1:
                stage=candidates[0]['stage']
                stage_origin='sidecar_overview_unique_source_record'
            elif len(candidates)>1:
                out['decision']='SOURCE_METADATA_AMBIGUOUS_STAGE_REVIEW_REQUIRED'
                return out
            elif same_serial:
                out['decision']='SOURCE_METADATA_CONFLICT_REVIEW_REQUIRED'
                return out
        if stage is None:
            out['decision']='STAGE_RECORD_PROVENANCE_INCOMPLETE'
            return out
    out['stage']=stage
    out['stage_origin']=stage_origin
    key=(stage,location['serial'])
    row=overview.get(key)
    if row is None:
        out['decision']='OVERVIEW_COMPOSITE_KEY_NOT_FOUND'
        return out
    out['overview_composite_key_found']=True
    out['sidecar_lab_matches_overview']=lab is not None and _identity(lab)==_identity(row['lab'])
    out['sidecar_internal_id_matches_overview']=internal is not None and _identity(internal)==_identity(row['serial_internal'])
    out['sidecar_testpoint_matches_overview']=(tp is not None and row['tp'] is not None
                                               and _norm_testpoint(tp)==_norm_testpoint(row['tp']))
    out['source_record_identity_cross_linked']=(out['sidecar_lab_matches_overview']
                                                and out['sidecar_internal_id_matches_overview'])
    if ((lab is not None and not out['sidecar_lab_matches_overview']) or
        (internal is not None and not out['sidecar_internal_id_matches_overview'])):
        out['decision']='SOURCE_METADATA_CONFLICT_REVIEW_REQUIRED'
    elif out['source_record_identity_cross_linked'] and tp is not None and row['tp'] is not None and not out['sidecar_testpoint_matches_overview']:
        # Authoritative source testpoint may use a different label convention.
        # Three exact identity fields are cross-linked, but phase/protocol remains unverified.
        out['decision']='SOURCE_IDENTIFIERS_LINKED_TESTPOINT_FORMAT_REVIEW_REQUIRED'
    elif out['source_record_identity_cross_linked']:
        out['decision']='SOURCE_RECORDS_CROSS_LINKED_NOT_PHYSICAL_AUTHENTICATION'
    else:
        out['decision']='SOURCE_METADATA_LINK_INCOMPLETE'
    return out


def run() -> dict:
    """Real publisher probe: ~30KB overview + 3 x ~7MB MD5+CRC verified archives."""
    from research.battery_curve_audit.figshare_three_archive_probe import (
        URL,PINNED,MAX_META_BYTES,MAX_SOURCE_BYTES,
        fetch_bounded,validate_source_meta,inspect_zip)
    from research.battery_curve_audit.figshare25975315_small_csv import (
        CSV_FILE_ID,MAX_ORIGINAL_CSV_BYTES,locate_publisher_file,inspect_original_csv)
    article_raw=fetch_bounded(URL,MAX_META_BYTES)
    article=json.loads(article_raw)
    pins=validate_source_meta(article)
    overview_pub=locate_publisher_file(article)
    overview_raw=fetch_bounded('https://ndownloader.figshare.com/files/'+str(CSV_FILE_ID),MAX_ORIGINAL_CSV_BYTES)
    overview_check=inspect_original_csv(overview_raw,overview_pub)
    overview=read_overview(overview_raw)
    source_results=[]
    for pub in pins:
        zip_raw=fetch_bounded('https://ndownloader.figshare.com/files/'+str(pub['id']),MAX_SOURCE_BYTES)
        orig=inspect_zip(zip_raw,pub)
        stem=pub['name'][:-4]
        with ZipFile(io.BytesIO(zip_raw)) as z:
            src=verify_cell_directory(z,stem)
        sidecar=summarize_meta_sidecar(src.pop('sidecar_bytes'))
        evidence=reconcile_records(src,overview,sidecar)
        source_results.append({'publisher_archive_id':pub['id'],
                               'original_zip_sha256':orig['original_zip_sha256'],
                               'paired_meta_sha256':src['sidecar_sha256'],
                               'sidecar_label_count':len(sidecar['field_keys']),
                               'sidecar_line_count':sidecar['line_count'],
                               'sidecar_encoding':sidecar['encoding'],
                               'sidecar_source_labels_only':sidecar['field_keys'],
                               **{k:v for k,v in evidence.items() if k!='sidecar_label_keys'}})
    return {'schema':'cano.battery.figshare279.original-three-source-identity-crosswalk.v1',
            'publisher_article_id':25975315,
            'original_publisher_overview_sha256':overview_check['original_file_sha256'],
            'overview_original_publisher_md5_matches':True,
            'overview_rows':len(overview),
            'composite_stage_serial_key_rows':len(overview),
            'publisher_archive_identities':source_results,
            'all_archive_md5_crc_verified':True,
            'overview_source_names_joined':sum(x['overview_composite_key_found'] for x in source_results),
            'sidecar_lab_and_internal_fields_both_matched':sum(x['sidecar_lab_matches_overview'] and x['sidecar_internal_id_matches_overview'] for x in source_results),
            'source_record_identity_cross_linked':sum(x['source_record_identity_cross_linked'] for x in source_results),
            'sidecar_testpoint_field_exactly_matches_overview':sum(x['sidecar_testpoint_matches_overview'] for x in source_results),
            'unresolved_join_or_format_count':sum(x['decision']!='SOURCE_RECORDS_CROSS_LINKED_NOT_PHYSICAL_AUTHENTICATION' for x in source_results),
            'physical_cells_independently_authenticated':0,
            'independent_lab_institution_authenticated':False,
            'field_FPR_FNR_established':False,
            'field_acceptance':'NOT_ESTABLISHED',
            'production_release_allowed':False,
            'decision':'SOURCE_METADATA_CROSSWALK_ONLY_NOT_FIELD_CERTIFICATION'}


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        print('usage: python -m research.battery_curve_audit.figshare_identity_provenance output.json', file=sys.stderr)
        return 2
    try:
        dst=Path(args[0])
        if dst.exists() or not dst.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: destination already exists or parent absent')
        result=run()
        with dst.open('x',encoding='utf-8') as fh:
            json.dump(result,fh,sort_keys=True,indent=2)
            fh.write('\n')
        print('PUBLISHER_STAGE_SERIAL_SIDECAR_CROSSWALK',
              'joined',result['overview_source_names_joined'],
              'both_fields_matched',result['sidecar_lab_and_internal_fields_both_matched'],
              'decisions',[x['decision'] for x in result['publisher_archive_identities']])
        return 0
    except (OSError,ValueError,TypeError,KeyError,UnicodeError,csv.Error) as err:
        print('SOURCE_REVIEW_REQUIRED:',str(err)[:180],file=sys.stderr)
        return 2


if __name__=='__main__':raise SystemExit(main())