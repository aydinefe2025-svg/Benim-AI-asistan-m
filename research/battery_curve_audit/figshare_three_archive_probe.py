"""Inspect three ORIGINAL publisher Figshare cell ZIPs; no raw data are published.

Bounded 3-archive source proof only. No independence, field false-match, or certification claims.
"""
from __future__ import annotations
import csv
from hashlib import md5, sha256
import io
import json
import re
from pathlib import Path, PurePosixPath
import stat
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile, BadZipFile
from research.battery_curve_audit.figshare_waveform_inventory import (
    analyze_inventory, URL, MAX_META_BYTES)

# Identified from official source-only inventory SHA da89d331...; IDs, byte size and MD5 pinned.
PINNED = (
    (47627092, 'TP_k01_05.zip', 7042134, 'fe9d2c2d84050af909926795a55a0e58'),
    (47627089, 'TP_k01_06.zip', 7060793, '940dd27960c7c13cacc611cb33f99796'),
    (47639005, 'TP_k01_04.zip', 7150834, '8e4f64b05547738d52f8e34a53c578d9'),
)
MAX_SOURCE_BYTES = 8_000_000
MAX_MEMBER_BYTES = 100_000_000
MAX_TOTAL_UNCOMPRESSED = 150_000_000
MAX_MEMBERS = 800
ALLOWED_CDN = '44c1cec316ec56bca76dfd65d2882b20.r2.cloudflarestorage.com'


def validate_source_meta(meta:dict) -> list[dict]:
    report=analyze_inventory(meta)
    if report['license']!='CC_BY_4_0_PUBLISHER_METADATA':
        raise ValueError('SOURCE_REVIEW_REQUIRED: no source license')
    by_id={x['id']:x for x in meta['files']}
    out=[]
    for fid,name,size,digest in PINNED:
        x=by_id.get(fid)
        if not x or x.get('name')!=name or x.get('size')!=size:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher file ID/name/size mismatch')
        d=x.get('computed_md5') or x.get('supplied_md5')
        if not isinstance(d,str) or d.lower()!=digest:
            raise ValueError('SOURCE_REVIEW_REQUIRED: publisher original MD5 changed')
        out.append({'id':fid,'name':name,'size':size,'md5':digest})
    return out


def fetch_bounded(url, limit):
    req=Request(url,headers={'Accept':'application/json' if url==URL else 'application/zip',
                             'User-Agent':'CANO-battery-original-small-waveform/1.0'})
    with urlopen(req,timeout=45) as response:
        uri=urlparse(response.geturl())
        valid_host=(uri.hostname=='api.figshare.com') if url==URL else (
            uri.hostname in {'ndownloader.figshare.com','figshare.com',ALLOWED_CDN})
        if response.status!=200 or uri.scheme!='https' or not valid_host:
            raise ValueError('SOURCE_REVIEW_REQUIRED: untrusted publisher redirect')
        raw=response.read(limit+1)
        if len(raw)>limit:
            raise ValueError('SOURCE_REVIEW_REQUIRED: source exceeds byte cap')
        return raw


def inspect_zip(raw:bytes, expected:dict) ->dict:
    if len(raw)!=expected['size'] or md5(raw).hexdigest()!=expected['md5']:
        raise ValueError('SOURCE_REVIEW_REQUIRED: original bytes/MD5 mismatch')
    try:
        with ZipFile(io.BytesIO(raw)) as z:
            entries=z.infolist()
            if not entries or len(entries)>MAX_MEMBERS:
                raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP member count')
            seen=set();expanded=0; csv_paths=[];meta_paths=[]
            for e in entries:
                name=e.filename
                p=PurePosixPath(name)
                if (p.is_absolute() or '\\' in name or any(x in {'','..'} for x in p.parts)
                    or name in seen or e.flag_bits&1 or stat.S_ISLNK(e.external_attr>>16)):
                    raise ValueError('SOURCE_REVIEW_REQUIRED: unsafe ZIP member')
                seen.add(name)
                if e.file_size>MAX_MEMBER_BYTES:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: large decompressed member')
                expanded+=e.file_size
                if expanded>MAX_TOTAL_UNCOMPRESSED:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP expansion budget')
                if e.file_size>1_000_000 and e.file_size>max(e.compress_size,1)*250:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP compression ratio')
                if not e.is_dir():
                    if name.lower().endswith('.csv'): csv_paths.append(name)
                    if name.lower().endswith('_meta.txt'): meta_paths.append(name)
            # After upfront bounded expansion check, test original archive's CRC without extracting.
            bad=z.testzip()
            if bad is not None:
                raise ValueError('SOURCE_REVIEW_REQUIRED: ZIP CRC failure')
            examples=[]
            for name in sorted(csv_paths)[:4]:
                with z.open(name) as fh:
                    with io.TextIOWrapper(fh, encoding='utf-8-sig', errors='replace', newline='') as stream:
                        header=next(csv.reader(stream,delimiter=','),[])
                examples.append({'ext':'csv','field_names_first_40':header[:40],
                                 'header_count':len(header),
                                 'time_alias_present':any('time' in x.lower() or x.lower() in {'t','c_t'} for x in header),
                                 'voltage_alias_present':any(x.lower() in {'c_vol','voltage','voltage_v','u','voltage [v]'} for x in header),
                                 'filename':PurePosixPath(name).name})
            return {'publisher_file_id':expected['id'],'publisher_name':expected['name'],
                    'original_zip_bytes':len(raw),'publisher_md5_matched':True,
                    'original_zip_sha256':sha256(raw).hexdigest(),
                    'zip_crc_passed':True,'zip_members':len(entries),
                    'zip_total_uncompressed_bytes':expanded,
                    'csv_count':len(csv_paths),'metadata_txt_count':len(meta_paths),
                    'csv_header_examples':examples,
                    'contains_csv_and_meta':bool(csv_paths and meta_paths)}
    except BadZipFile as e:
        raise ValueError('SOURCE_REVIEW_REQUIRED: bad ZIP container') from e


def run():
    meta_raw=fetch_bounded(URL,MAX_META_BYTES)
    meta=json.loads(meta_raw)
    pinned=validate_source_meta(meta)
    samples=[]
    for x in pinned:
        raw=fetch_bounded(f"https://ndownloader.figshare.com/files/{x['id']}",MAX_SOURCE_BYTES)
        samples.append(inspect_zip(raw,x))
    return {'schema':'cano.battery.figshare279.original-three-small-archive-probe.v1',
            'source_doi':meta.get('doi'),'original_metadata_sha256':sha256(meta_raw).hexdigest(),
            'original_archives_verified':len(samples),'files':samples,
            'waveform_signal_rows_compared':0,
            'independent_physical_cells_authenticated':0,
            'empirical_cross_cell_confusion_established':False,
            'field_acceptance':'NOT_ESTABLISHED',
            'decision':'THREE_ORIGINAL_ARCHIVE_CONTENTS_VERIFIED_SOURCE_ONLY',
            'production_release_allowed':False}


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        print('usage: python -m research.battery_curve_audit.figshare_three_archive_probe OUTPUT.json',file=sys.stderr)
        return 2
    try:
        dst=Path(args[0])
        if dst.exists() or not dst.parent.is_dir():
            raise ValueError('SOURCE_REVIEW_REQUIRED: destination exists/parent invalid')
        report=run()
        with dst.open('x',encoding='utf-8') as f:
            json.dump(report,f,indent=2,sort_keys=True)
            f.write('\n')
        print('THREE_ORIGINAL_ARCHIVES_SOURCE_ONLY',json.dumps({
            'count':report['original_archives_verified'],
            'csv_counts':[f['csv_count'] for f in report['files']],
            'meta_counts':[f['metadata_txt_count'] for f in report['files']]}))
        return 0
    except (ValueError,KeyError,TypeError,UnicodeError,OSError,BadZipFile,json.JSONDecodeError,csv.Error) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:180],file=sys.stderr)
        return 2

if __name__=='__main__': raise SystemExit(main())