"""Reconcile Vienna-local original electrical log windows and SP start epochs.

Outputs start-time candidate matches only; never claims proven sensor synchronization.
"""
from __future__ import annotations
import argparse, calendar, datetime as dt, json, re
from pathlib import Path

# Pure-stdlib EU/CET rule for the 2024-2025 original measurements. Windows
# GitHub-hosted Python has no system IANA tzdb and this project uses no pip deps.
# Fail closed on DST ambiguous/nonexistent local times, never guess a fold.
def _last_sunday(year: int, month: int) -> int:
    day = calendar.monthrange(year, month)[1]
    return day - (dt.date(year, month, day).weekday() + 1) % 7

def vienna_epoch(local: dt.datetime) -> float:
    if local.tzinfo is not None or not (1996 <= local.year <= 2030):
        raise ValueError('unsupported local Vienna date')
    spring = dt.datetime(local.year, 3, _last_sunday(local.year, 3), 2)
    autumn = dt.datetime(local.year, 10, _last_sunday(local.year, 10), 3)
    hour = dt.timedelta(hours=1)
    if spring <= local < spring + hour or autumn - hour <= local < autumn:
        raise ValueError('nonexistent or ambiguous Vienna DST hour')
    utc_offset_h = 2 if spring + hour <= local < autumn - hour else 1
    return local.replace(tzinfo=dt.timezone(dt.timedelta(hours=utc_offset_h))).timestamp()

SP_PATTERN = re.compile(r'_(\d{2})_(\d{2})_(\d{4})_(\d{2})_(\d{2})_(\d{2})_logfile\.txt$',re.I)

def parse_log_token(s: str) -> float:
    return vienna_epoch(dt.datetime.strptime(s,'%Y-%m-%d_%H-%M-%S-%f'))

def parse_sp(item: dict) -> tuple[float,float]:
    values = [x['text'] for x in item.get('metadata_line_clues',[]) if x['text'].strip().startswith('Start time')]
    if len(values)!=1:
        raise ValueError('SP source epoch start metadata missing/ambiguous')
    start = float(values[0].split(':',1)[1].strip())
    match = SP_PATTERN.search(item['path'])
    if not match:
        raise ValueError('SP start file date missing/ambiguous')
    dd,mm,yyyy,hh,mi,ss=map(int,match.groups())
    filename_local=vienna_epoch(dt.datetime(yyyy,mm,dd,hh,mi,ss))
    if abs(filename_local-start)>1.5:
        raise ValueError('SP embedded epoch not consistent with publisher file date / Vienna timezone')
    return start,abs(filename_local-start)

def verify_starts(source: dict) -> dict:
    if not source.get('publisher_zip_md5_verified') or not source.get('zip_crc_verified') or source.get('source_doi')!='10.5281/zenodo.22079387':
        raise ValueError('source original checksum proof required')
    src = source.get('members',[])
    checked={}; all_sp=[]; all_logs=[]
    for cell in ('02','03'):
        own=[x for x in src if x.get('cell_id_from_name_only')==cell]
        logs=[x for x in own if x.get('candidate_role_from_name_only')=='charge_discharge_log_candidate']
        sps=[x for x in own if x.get('candidate_role_from_name_only')=='thickness_sp_candidate']
        if len(logs)!=1 or len(sps)!=3:
            raise ValueError('source full electrical/SP file set not present for each physical cell')
        lo=parse_log_token(logs[0]['first_electrical_time_token'])
        hi=parse_log_token(logs[0]['last_electrical_time_token'])
        if hi <= lo:
            raise ValueError('bad source electrical time interval')
        windows=[]
        for sp in sps:
            start,filename_disagreement=parse_sp(sp)
            valid = lo<=start<=hi
            windows.append({'sp_file':sp['path'].split('/')[-1],
                'sp_start_epoch_s':start,'sp_filename_epoch_difference_s':filename_disagreement,
                'starts_in_same_cell_electrical_log_window':valid,
                'required_full_sp_duration_and_signal_phase_join_verified':False})
            all_sp.append((cell,start))
        all_logs.append((cell,lo,hi))
        checked[cell]={'source_label':cell,'log_start_epoch_s':lo,'log_end_epoch_s':hi,
                       'total_sp_files':len(windows),'sp_start_inside_count':sum(x['starts_in_same_cell_electrical_log_window'] for x in windows),
                       'sp_start_outside_count':sum(not x['starts_in_same_cell_electrical_log_window'] for x in windows),
                       'sp_files':windows}
    cross_cell=0; wrong_phase_same=0; valid_starts=0
    for source_cell,lo,hi in all_logs:
        for sp_cell,start in all_sp:
            if sp_cell!=source_cell:cross_cell+=1
            elif not lo<=start<=hi:wrong_phase_same+=1
            else:valid_starts+=1
    return {'source_doi':source['source_doi'],'source_zip_sha256':source['original_zip_sha256'],
        'target_cells':['02','03'],'time_basis':'Europe/Vienna wallclock (.log) versus SP Unix epoch, verified against SP filename to <=1.5s',
        'cells':checked,'all_cartesian_log_sp_pairs':len(all_logs)*len(all_sp),
        'source_label_wrong_cell_pairs':cross_cell,'same_cell_sp_starts_outside_log':wrong_phase_same,
        'same_cell_sp_starts_inside_log_candidates':valid_starts,
        'structurally_invalid_all_pairs':cross_cell+wrong_phase_same,
        'full_sp_interval_and_signal_sync_verified':False,
        'experiment_phase_alignment_certified':False,
        'is_not_a_measured_field_false_positive_rate':True,
        'is_not_an_impact_or_causal_capacity_test':True}

def main():
    p=argparse.ArgumentParser();p.add_argument('original_provenance_json',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    d=verify_starts(json.loads(a.original_provenance_json.read_text(encoding='utf-8')))
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(d,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print('REAL_SOURCE_SP_START_TIME_GATE',d['same_cell_sp_starts_inside_log_candidates'],'inside',d['same_cell_sp_starts_outside_log'],'outside',d['source_label_wrong_cell_pairs'],'wrong-cell Cartesian pairs')
    print('NOT_FULL_PHASE_OR_SIGNAL_SYNCHRONIZATION')

if __name__=='__main__':main()