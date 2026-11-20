"""Nine source-backed ET/AT capacity comparisons in 3 NEW original k04 cells.

The original publisher's 3 k04 zip files are 34.8MB, distinct from prior k01.
All source archives are publisher MD5-pinned, ZIP CRC checked and bounded. A
source-sidecar lab, internal serial, testpoint and T are checked for every pair.
This is a descriptive measurement comparison, not storage-only degradation,
independently witnessed physical identity, or field FPR/FNR certification.
"""
from __future__ import annotations
from datetime import datetime
from hashlib import md5, sha256
from pathlib import Path, PurePosixPath
from zipfile import ZipFile
import io, json, re, sys

from research.battery_curve_audit.figshare_next_cohort_preflight import (
    inspect_metadata, MAX_METADATA_BYTES,
)
from research.battery_curve_audit.figshare_three_archive_probe import (
    URL, fetch_bounded, inspect_zip,
)
from research.battery_curve_audit.figshare_k01_et_at_capacity import (
    inspect_phase, _meta_record,
)
from research.battery_curve_audit.figshare_identity_provenance import (
    summarize_meta_sidecar,
)

ORIGINALS=(
    (47627107,'TP_k04_04.zip',11639567,'7548b71684cf9a47fb89c192594ad649'),
    (47627110,'TP_k04_05.zip',11468262,'93956f361b84a623b258c53e0193225c'),
    (47627104,'TP_k04_06.zip',11660912,'17c9445e56c1d3ed6292ac0cf5046fc8'),
)
TEMPERATURES=(10,23,45)
MAX_ORIGINAL_BYTES=15_000_000


def parse_sidecar(z:ZipFile,source_file:str,temp:int)->dict:
    meta=_meta_record(z,source_file)
    p=source_file[:-4]+'_meta.txt'
    fields=summarize_meta_sidecar(z.read(p))['parsed_fields']
    point=str(fields.get('testpoint') or '').strip().casefold().replace(' ','')
    # Publisher original sidecar uses 'k04'; the 04-06 no-intermediate-CU
    # protocol is documented separately in the paper, not encoded here.
    if point!='k04':
        raise ValueError('SOURCE_REVIEW_REQUIRED: incorrect source calendar k04 protocol label; published=' + repr(point[:40]))
    temp_text=str(meta.get('temperature') or '').strip().replace(' ','')
    m=re.fullmatch(r'(\d+(?:\.\d+)?)°C',temp_text)
    if not m or float(m.group(1))!=temp:
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong source climate chamber temperature')
    date_str=str(fields.get('measurement_start_date') or '').strip()
    date=None
    if date_str:
        for fmt in ('%d.%m.%Y','%d.%m.%y'):
            try:
                date=datetime.strptime(date_str,fmt).date()
                break
            except ValueError:
                pass
        if date is None:
            raise ValueError('SOURCE_REVIEW_REQUIRED: unparseable published measurement date')
    return {'lab':meta['lab'],'serial':meta['serial'],'sidecar_sha256':meta['paired_meta_sha256'],
            'date':date,'temperature_C':temp,'protocol_label':point}


def analyze_new_cell(z:ZipFile,stem:str)->list[dict]:
    if not re.fullmatch(r'TP_k04_0[456]',stem):
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong new source cohort')
    names=z.namelist()
    if len(set(names))!=len(names):
        raise ValueError('SOURCE_REVIEW_REQUIRED: duplicated source member')
    known_identity=None
    profiles=[]
    for t in TEMPERATURES:
        data={}
        for phase in ('ET','AT'):
            pattern=re.compile(re.escape(stem)+r'_\d{2}_'+phase+r'_T'+str(t)+r'\.csv$')
            matches=[n for n in names if pattern.fullmatch(PurePosixPath(n).name)]
            if len(matches)!=1:
                raise ValueError('SOURCE_REVIEW_REQUIRED: missing or ambiguous original ET/AT pair')
            filename=matches[0]
            side=parse_sidecar(z,filename,t)
            identity=(side['lab'],side['serial'],side['protocol_label'])
            if known_identity is None:known_identity=identity
            if identity!=known_identity:
                raise ValueError('SOURCE_REVIEW_REQUIRED: source internal serial / lab / protocol mismatch')
            measure=inspect_phase(z,filename)
            if not measure['source_capacity_extractable']:
                raise ValueError('SOURCE_REVIEW_REQUIRED: invalid original charge/discharge capacity phase')
            data[phase]={'source_name':PurePosixPath(filename).name,'sidecar':side,'measure':measure}
        et=data['ET'];at=data['AT'];q0=et['measure']['capacity_mean_Ah'];q1=at['measure']['capacity_mean_Ah']
        c0=et['measure']['step21_charging']['capacity_Ah'];c1=at['measure']['step21_charging']['capacity_Ah']
        d0=et['measure']['step22_discharging']['capacity_Ah'];d1=at['measure']['step22_discharging']['capacity_Ah']
        mc=round(100*(q1/q0-1),4);cc=round(100*(c1/c0-1),4);dc=round(100*(d1/d0-1),4)
        if cc<0 and dc<0: direction='BOTH_CHANNELS_DECLINE_OBSERVED'
        elif cc>0 and dc>0: direction='BOTH_CHANNELS_INCREASE_OBSERVED'
        else: direction='CHANNEL_DIRECTION_MISMATCH_REVIEW_REQUIRED'
        dt0=et['sidecar']['date'];dt1=at['sidecar']['date']
        if dt0 is not None and dt1 is not None and dt1<=dt0:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source AT date not after ET date')
        profiles.append({
            'temperature_C':t,
            'et_source_filename':et['source_name'],'at_source_filename':at['source_name'],
            'source_lab_and_internal_serial_match':True,
            'et_sidecar_sha256':et['sidecar']['sidecar_sha256'],
            'at_sidecar_sha256':at['sidecar']['sidecar_sha256'],
            'et_to_at_days':(dt1-dt0).days if dt0 and dt1 else None,
            'source_date_chronology_checked':dt0 is not None and dt1 is not None,
            'original_csv_rows':et['measure']['source_rows_processed']+at['measure']['source_rows_processed'],
            'et_mean_capacity_Ah':q0,'at_mean_capacity_Ah':q1,
            'et_charge_capacity_Ah':c0,'at_charge_capacity_Ah':c1,
            'et_discharge_capacity_Ah':d0,'at_discharge_capacity_Ah':d1,
            'mean_change_percent':mc,'charge_change_percent':cc,'discharge_change_percent':dc,
            'channel_direction':direction,
            'physical_cell_identity_independently_authenticated':False,
            'storage_only_aging_loss_proven':False,
            'field_FPR_FNR_established':False,
        })
    return profiles


def pinned_metadata(meta:dict):
    examined=inspect_metadata(meta)
    selected=examined['chosen_cohort']
    if not selected or selected['testpoint']!='TP_k04':
        raise ValueError('SOURCE_REVIEW_REQUIRED: expected first distinct k04 cohort absent')
    actual={(x['id'],x['filename'],x['size_bytes'],x['publisher_md5'])
            for x in selected['original_publisher_files']}
    expected={(fid,name,size,digest) for fid,name,size,digest in ORIGINALS}
    if actual!=expected:
        raise ValueError('SOURCE_REVIEW_REQUIRED: pinned k04 original publisher sources changed')
    return examined


def run(save_originals:Path|None=None):
    raw_meta=fetch_bounded(URL,MAX_METADATA_BYTES)
    meta=json.loads(raw_meta)
    approved=pinned_metadata(meta)
    if save_originals is not None and (not save_originals.is_dir() or list(save_originals.iterdir())):
        raise ValueError('SOURCE_REVIEW_REQUIRED: save directory must exist and be empty')
    cells=[]
    for fid,name,size,digest in ORIGINALS:
        raw=fetch_bounded('https://ndownloader.figshare.com/files/'+str(fid),MAX_ORIGINAL_BYTES)
        record={'id':fid,'name':name,'size':size,'md5':digest}
        validated=inspect_zip(raw,record)
        if len(raw)!=size or md5(raw).hexdigest()!=digest:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher hash not matched')
        with ZipFile(io.BytesIO(raw)) as z:
            profiles=analyze_new_cell(z,name[:-4])
        if save_originals is not None:
            (save_originals/name).write_bytes(raw)
        cells.append({'publisher_file_id':fid,'publisher_filename':name,'archive_size_bytes':size,
                      'archive_sha256':validated['original_zip_sha256'],
                      'publisher_md5_matched':True,'zip_crc_checked':True,
                      'source_profiles':profiles})
    allp=[p for c in cells for p in c['source_profiles']]
    return {'schema':'cano.battery.figshare25975315.original-k04-three-cell-etat-channel-audit.v1',
            'publisher_article_id':25975315,'publisher_doi':meta['doi'],
            'publisher_metadata_sha256':sha256(raw_meta).hexdigest(),
            'cohort':'TP_k04','source_archives':cells,'original_archives_verified':3,
            'source_cells':3,'source_temperature_pairs':len(allp),
            'source_csv_files_processed':len(allp)*2,
            'original_timestamp_voltage_current_rows_processed':sum(p['original_csv_rows'] for p in allp),
            'mean_negative_pairs':sum(p['mean_change_percent']<0 for p in allp),
            'both_channels_negative_pairs':sum(p['channel_direction']=='BOTH_CHANNELS_DECLINE_OBSERVED' for p in allp),
            'mixed_or_zero_direction_pairs':sum(p['channel_direction']=='CHANNEL_DIRECTION_MISMATCH_REVIEW_REQUIRED' for p in allp),
            'chronology_checked_pairs':sum(p['source_date_chronology_checked'] for p in allp),
            'external_physical_sample_identity_authenticated':False,
            'field_FPR_FNR_established':False,'production_release_allowed':False,
            'causal_storage_only_aging_established':False,
            'decision':'NEW_K04_ORIGINAL_THREE_CELL_SOURCE_RESEARCH_ONLY'}


def main(argv=None):
    a=list(sys.argv[1:] if argv is None else argv)
    try:
        if len(a) not in (1,3) or (len(a)==3 and a[1]!='--archive-dir'):
            raise ValueError('usage: python -m research.battery_curve_audit.figshare_k04_original_capacity RESULT.json [--archive-dir EMPTY_DIR]')
        path=Path(a[0])
        if path.exists() or not path.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: result must not exist')
        save=Path(a[2]) if len(a)==3 else None
        out=run(save)
        with path.open('x',encoding='utf-8') as f:
            json.dump(out,f,indent=2,sort_keys=True);f.write('\n')
        print('NEW_SOURCE_COHORT_ORIGINAL_K04',json.dumps({
            'cells':out['source_cells'],'csv':out['source_csv_files_processed'],
            'rows':out['original_timestamp_voltage_current_rows_processed'],
            'mean_losses':out['mean_negative_pairs'],
            'both_channel_losses':out['both_channels_negative_pairs'],
            'mixed_channels':out['mixed_or_zero_direction_pairs'],
            'chronology_checked_pairs':out['chronology_checked_pairs'],
            'per_source':[(c['publisher_file_id'],[(p['temperature_C'],p['mean_change_percent'],p['charge_change_percent'],p['discharge_change_percent']) for p in c['source_profiles']]) for c in out['source_archives']]},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:200],file=sys.stderr)
        return 2
if __name__=='__main__':raise SystemExit(main())