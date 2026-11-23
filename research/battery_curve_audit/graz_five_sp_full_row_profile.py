"""Original Graz five-cell SP physical timestamp/column audit.

Official 2026 Zenodo DOI 10.5281/zenodo.22079387: one independent source
archive, five source labels, 15 SP logs. The true SP Time column is an unzoned
calendar timestamp encoded as TWO whitespace tokens (DD/MM/YYYY HH:MM:SS),
followed by two position and three sensor numbers. Match only source labels.
Do not infer synchronized instrument clocks, force calibration, state of health,
causal mechanical effect, impact, or nine/Forty-eight cell cross-dataset joins.
"""
from __future__ import annotations
import argparse, collections, datetime as dt, hashlib, io, json, math, pathlib, re, zipfile
from research.battery_curve_audit import graz_five_cell_original_preflight as core
from research.battery_curve_audit import graz_five_cell_numeric_probe as prior

GOAL = 'graz-20261123-original-15-SP-measurement-row-profiling'
DATA_HEADER = re.compile(r'^\s*Time\s+Position\s*X\s*\[mm\]\s+Position\s*Z\s*\[mm\]', re.I)
START_EPOCH = re.compile(r'^\s*Start\s+time\s*:\s*([0-9]+(?:\.[0-9]+)?)', re.I)
COLUMNS = ('Position X[mm]', 'PositionZ[mm]', 'Sensor 1[micro-m]', 'Sensor 2[micro-m]', 'Sensor 3[micro-m]')
MAX_SENSOR_ABS = 1_000_000_000


def isnum(x: str):
    try: v=float(x)
    except (ValueError, TypeError): return None
    return v if math.isfinite(v) and abs(v) < MAX_SENSOR_ABS else None


def parse_sp_timestamp(date_token: str, time_token: str) -> dt.datetime:
    # SP source is European DD/MM/YYYY; never reinterpret as MM/DD/YYYY.
    try: return dt.datetime.strptime(date_token+' '+time_token, '%d/%m/%Y %H:%M:%S')
    except ValueError as exc: raise ValueError('invalid true SP absolute calendar timestamp') from exc


def profile_sp(z, member, electric_first: dt.datetime|None = None, electric_last: dt.datetime|None = None):
    counts=collections.Counter()
    start_epoch=None
    found_header=False
    examples=[]
    header_line=None
    first=last=earliest=latest=previous=None
    dimension_counts=collections.Counter()
    mins={k: None for k in COLUMNS}
    maxs={k: None for k in COLUMNS}
    max_positive_gap=0.0
    min_positive_gap=None
    for_window=(electric_first is not None and electric_last is not None)
    if for_window and not electric_first<electric_last:
        raise ValueError('electrical recording time interval reversed')
    with z.open(member) as f:
        for lineno, raw in enumerate(f, 1):
            if lineno > 3_000_000:
                raise ValueError('SP original file row cap exceeded')
            line=raw.decode('utf-8-sig',errors='replace').strip()
            if not found_header:
                m=START_EPOCH.match(line)
                if m:
                    if start_epoch is not None: raise ValueError('duplicate embedded SP Start time')
                    start_epoch=float(m.group(1))
                if DATA_HEADER.search(line):
                    found_header=True
                    header_line=line[:280]
                    counts['header_line_no']=lineno
                continue
            if not line: continue
            counts['post_header_lines']+=1
            if len(examples)<3: examples.append(line[:220])
            parts=line.split()
            dimension_counts[len(parts)]+=1
            if len(parts)!=7:
                counts['rows_wrong_token_count']+=1
                continue
            try: t=parse_sp_timestamp(parts[0],parts[1])
            except ValueError:
                counts['rows_invalid_timestamp']+=1
                continue
            v=[isnum(x) for x in parts[2:]]
            if any(x is None for x in v):
                counts['rows_invalid_numeric']+=1
                continue
            counts['valid_six_field_rows']+=1
            for col,x in zip(COLUMNS,v):
                mins[col]=x if mins[col] is None else min(mins[col],x)
                maxs[col]=x if maxs[col] is None else max(maxs[col],x)
            if first is None: first=t
            last=t
            earliest=t if earliest is None else min(earliest,t)
            latest=t if latest is None else max(latest,t)
            if previous is not None:
                sec=(t-previous).total_seconds()
                if sec<=0: counts['nonincreasing_time_steps']+=1
                else:
                    min_positive_gap=sec if min_positive_gap is None else min(sec,min_positive_gap)
                    max_positive_gap=max(sec,max_positive_gap)
            previous=t
            if for_window and electric_first <= t <= electric_last:
                counts['rows_inside_electrical_recording_window_candidate']+=1
    if start_epoch is None or not found_header:
        raise ValueError('original SP missing epoch start or expected source column header')
    if counts['valid_six_field_rows']<100:
        raise ValueError('unverified source SP data format: <100 valid rows')
    ranges={k:[mins[k],maxs[k]] for k in COLUMNS}
    flat=[k for k in COLUMNS if ranges[k][0]==ranges[k][1]]
    return {'source_member':member, 'original_schema_header':header_line,
            'embedded_start_epoch':start_epoch,
            'counts':dict(counts),
            'preview_only_first_three_original_source_lines':examples,
            'original_row_token_width_histogram':{str(k):v for k,v in sorted(dimension_counts.items())},
            'first_original_timestamp_unzoned':first.isoformat(),
            'last_original_timestamp_unzoned':last.isoformat(),
            'min_original_timestamp_unzoned':earliest.isoformat(),
            'max_original_timestamp_unzoned':latest.isoformat(),
            'smallest_positive_sample_gap_seconds':min_positive_gap,
            'largest_positive_sample_gap_seconds':max_positive_gap,
            'numeric_column_ranges_in_source_reported_units':ranges,
            'exact_constant_original_numeric_channels':flat,
            'electrical_time_window_comparison_performed':for_window,
            'electrical_and_SP_instrument_clocks_independently_synchronized':False,
            'source_sensor_absolute_calibration_verified':False,
            'mechanical_electrical_correlational_causality_unproven':True}


def inspect():
    meta=core.get_bytes(core.API, 2_000_000)
    spec=core.validate_manifest(json.loads(meta))
    blob=core.get_bytes(spec['download_url'],core.MAX_ZIP_BYTES)
    if len(blob)!=spec['size'] or hashlib.md5(blob).hexdigest()!=core.PUBLISHER_MD5:
        raise ValueError('source publisher byte length / MD5 failure')
    struct=core.audit_archive(blob)
    if not struct['zip_crc_all_members_pass']: raise ValueError('source ZIP CRC failure')
    cells={}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        groups=prior.filename_groups(z.infolist())
        for cell,g in sorted(groups.items()):
            elec=prior.scan_electrical_log(z,g['cycling_log'][0])
            elo=dt.datetime.fromisoformat(elec['first_valid_timestamp'])
            ehi=dt.datetime.fromisoformat(elec['last_valid_timestamp'])
            files=[profile_sp(z,n,elo,ehi) for n in sorted(g['sp_txt'])]
            cells[cell]={'source_publisher_preload_kN':core.PUBLISHER_CELLS[cell],
                         'electric_source_member':g['cycling_log'][0],
                         'electric_first_original_unzoned':elo.isoformat(),
                         'electric_last_original_unzoned':ehi.isoformat(),
                         'SP':files}
    return {'goal_key':GOAL,'source_doi':core.DOI,
            'source_md5':core.PUBLISHER_MD5,'source_sha256':hashlib.sha256(blob).hexdigest(),
            'source_zip_crc_all_members_pass':True,
            'num_physical_source_folders':len(cells),
            'sp_file_count':sum(len(c['SP']) for c in cells.values()),
            'sp_valid_numeric_rows':sum(f['counts']['valid_six_field_rows']
                                        for c in cells.values() for f in c['SP']),
            'sp_rows_inside_electrical_global_time_windows_candidate':sum(
                 f['counts'].get('rows_inside_electrical_recording_window_candidate',0)
                 for c in cells.values() for f in c['SP']),
            'cells':cells,
            'timezone_and_interinstrument_clock_sync_unverified':True,
            'source_sensor_absolute_calibration_unverified':True,
            'capacity_and_SOH_not_recomputed':True,
            'dynamic_impact_not_applied':True,
            'causal_preload_effect_not_identified':True,
            'dataset_separate_from_graz_4_cell_18315429':True}


def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=pathlib.Path)
    args=p.parse_args();data=inspect()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(data,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    print('REAL_GRAZ_SP_ROWS',data['sp_valid_numeric_rows'])
    print('REAL_GRAZ_SP_WITHIN_ELECTRIC_TIME_WINDOW_CANDIDATE_ROWS',data['sp_rows_inside_electrical_global_time_windows_candidate'])
    for cell,c in data['cells'].items():
        for sp in c['SP']:
            print('REAL_SOURCE_SP',cell,pathlib.PurePosixPath(sp['source_member']).name,
                  sp['counts'], sp['first_original_timestamp_unzoned'],sp['last_original_timestamp_unzoned'],
                  sp['exact_constant_original_numeric_channels'],flush=True)

if __name__=='__main__': main()