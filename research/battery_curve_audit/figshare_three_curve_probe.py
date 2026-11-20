"""Three original Figshare ET_T23 waveform windows, identity-blind pair comparisons.

No physical independence, diagnostic error rate, SOH or real lab certification claims.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha256
import csv
import io
import json
from pathlib import Path, PurePosixPath
import sys
from zipfile import ZipFile

from research.battery_curve_audit.figshare_three_archive_probe import (
    URL, PINNED, MAX_SOURCE_BYTES, MAX_META_BYTES, fetch_bounded,
    inspect_zip, validate_source_meta
)

SAMPLE_LIMIT = 20_000
MIN_ROWS = 1_000


def read_matched_window(z: ZipFile, filename: str, *, limit=SAMPLE_LIMIT) -> dict:
    names=set(z.namelist())
    if not filename.endswith('_ET_T23.csv') or '/' in filename or '\\' in filename:
        raise ValueError('REVIEW_REQUIRED: unsafe requested measurement name')
    matches=[n for n in names if PurePosixPath(n).name==filename]
    if len(matches)!=1:
        raise ValueError('REVIEW_REQUIRED: original ET_T23 file absent or ambiguous')
    original_path=matches[0]
    if PurePosixPath(original_path).is_absolute() or '..' in PurePosixPath(original_path).parts:
        raise ValueError('REVIEW_REQUIRED: unsafe source path')
    meta_name=original_path[:-4]+'_meta.txt'
    if meta_name not in names:
        raise ValueError('REVIEW_REQUIRED: source paired recording metadata missing')
    meta_sha=sha256(z.read(meta_name)).hexdigest()
    points=[]
    with z.open(original_path) as fh:
        text=io.TextIOWrapper(fh, encoding='utf-8-sig', errors='strict',newline='')
        reader=csv.DictReader(text)
        required={'run_time','c_vol','c_cur','step_type'}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError('REVIEW_REQUIRED: expected physical measurement columns missing')
        first_t,prev_t=None,None
        for row in reader:
            if len(points)==limit:break
            if None in row:raise ValueError('REVIEW_REQUIRED: malformed source row')
            try:
                t=Decimal(row['run_time'])
                v=Decimal(row['c_vol'])
                cur=Decimal(row['c_cur'])
            except (InvalidOperation,TypeError) as e:
                raise ValueError('REVIEW_REQUIRED: nonnumeric source time/voltage/current') from e
            if not all(x.is_finite() for x in (t,v,cur)):
                raise ValueError('REVIEW_REQUIRED: nonfinite source measurement')
            if first_t is None:first_t=t
            if prev_t is not None and t<prev_t:
                raise ValueError('REVIEW_REQUIRED: time axis goes backwards')
            points.append((t-first_t,v,cur,str(row['step_type'])))
            prev_t=t
    if len(points)<MIN_ROWS or len({x[0] for x in points})<2:
        raise ValueError('REVIEW_REQUIRED: source series too short or flat time axis')
    return {'count':len(points),'paired_meta_sha256':meta_sha,'points':points}


def compare_windows(left:dict,right:dict) ->dict:
    l,r=left['points'],right['points']
    comparable=len(l)==len(r) and all(a[0]==b[0] for a,b in zip(l,r))
    if comparable:
        equal_pairs=sum(a[1]==b[1] for a,b in zip(l,r))
        exact_all=equal_pairs==len(l)
        max_volt_diff=max(abs(a[1]-b[1]) for a,b in zip(l,r))
        return {'sample_count_each':len(l),'sampled_time_axis_exactly_equal':True,
                'exact_voltage_matches':equal_pairs,'exact_voltage_sequence_equal':exact_all,
                'max_absolute_voltage_difference_native_units':str(max_volt_diff)}
    return {'sample_count_each':min(len(l),len(r)),
            'sampled_time_axis_exactly_equal':False,
            'exact_voltage_matches':None,'exact_voltage_sequence_equal':None,
            'max_absolute_voltage_difference_native_units':None}


def run() ->dict:
    raw_meta=fetch_bounded(URL,MAX_META_BYTES)
    meta=json.loads(raw_meta)
    pinned=validate_source_meta(meta)
    windows=[];sources=[]
    for x in pinned:
        raw=fetch_bounded('https://ndownloader.figshare.com/files/'+str(x['id']),MAX_SOURCE_BYTES)
        archive=inspect_zip(raw,x)
        target=x['name'][:-4]+'_01_ET_T23.csv'
        with ZipFile(io.BytesIO(raw)) as z:
            # Do not trust target name unless source archive was MD5 & CRC verified.
            rec=read_matched_window(z,target)
        windows.append(rec)
        sources.append({'publisher_file_id':x['id'],'archive_sha256':archive['original_zip_sha256'],
                        'source_csv_name':target,'source_meta_sha256':rec['paired_meta_sha256'],
                        'bounded_rows_examined':rec['count'],'csv_header_verified':True})
    comparisons=[]
    for i in range(len(windows)):
        for j in range(i+1,len(windows)):
            comparisons.append({'left_file_id':sources[i]['publisher_file_id'],
                                'right_file_id':sources[j]['publisher_file_id'],
                                **compare_windows(windows[i],windows[j])})
    return {'schema':'cano.battery.figshare279.real-3-original-ET23-window-comparison.v1',
            'article_id':25975315,'source_doi':meta['doi'],
            'publisher_metadata_sha256':sha256(raw_meta).hexdigest(),
            'source_archives':sources,'pairwise_results':comparisons,
            'total_pairs':len(comparisons),'time_unit_authoritatively_verified':False,
            'source_archive_identifier_is_not_independent_human_cell_authentication':True,
            'physical_cell_independence_authenticated':False,
            'empirical_field_FPR_FNR_established':False,
            'field_acceptance':'NOT_ESTABLISHED',
            'decision':'REAL_ORIGINAL_WINDOWS_SCREENED_RESEARCH_ONLY',
            'production_release_allowed':False}


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        print('usage: python -m research.battery_curve_audit.figshare_three_curve_probe report.json',file=sys.stderr)
        return 2
    try:
        dest=Path(args[0])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError('REVIEW_REQUIRED: destination not exclusive')
        result=run()
        with dest.open('x',encoding='utf-8') as f:
            json.dump(result,f,indent=2,sort_keys=True)
            f.write('\n')
        print('REAL_ORIGINAL_WINDOWS_RESEARCH_ONLY',json.dumps(result['pairwise_results']))
        return 0
    except (OSError,ValueError,TypeError,KeyError,csv.Error) as e:
        print('REVIEW_REQUIRED:',str(e)[:180],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())