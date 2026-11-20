"""Bounded publisher-only metadata preflight for previously unstudied battery cohorts.
No raw source cells are downloaded, no physical identity or lab validation inferred.
"""
from __future__ import annotations
from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import json, re, sys

API='https://api.figshare.com/v2/articles/25975315'
DOI_RE=r'10\.6084/m9\.figshare\.25975315(?:\.v\d+)?'
NAME_RE=re.compile(r'^TP_k(\d{2})_0([456])\.zip$')
MAX_METADATA_BYTES=2_000_000
MAX_SINGLE_BYTES=15_000_000
MAX_COHORT_BYTES=42_000_000


def inspect_metadata(meta:dict,raw_sha256:str='') -> dict:
    if not isinstance(meta,dict) or meta.get('id')!=25975315 or not re.fullmatch(DOI_RE,str(meta.get('doi','')).lower()):
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong publisher article')
    lic=meta.get('license') or {}
    if not isinstance(lic,dict) or '4.0' not in str(lic.get('name','')) or '/by/4.0' not in str(lic.get('url','')):
        raise ValueError('SOURCE_REVIEW_REQUIRED: publisher CC BY 4.0 licence missing')
    files=meta.get('files')
    if not isinstance(files,list) or not 1<=len(files)<=5000:
        raise ValueError('SOURCE_REVIEW_REQUIRED: unexpected publisher file list')
    by_group=defaultdict(dict)
    seen_ids=set();name_counts=defaultdict(int)
    for x in files:
        if not isinstance(x,dict):raise ValueError('SOURCE_REVIEW_REQUIRED: malformed publisher file')
        fid,name,size=x.get('id'),x.get('name'),x.get('size')
        if type(fid) is not int or fid<=0 or not isinstance(name,str) or type(size) is not int or size<0:
            raise ValueError('SOURCE_REVIEW_REQUIRED: invalid source metadata types')
        if fid in seen_ids or '/' in name or '\\' in name or '..' in name:
            raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate or unsafe source listing')
        seen_ids.add(fid);name_counts[name]+=1
        match=NAME_RE.fullmatch(name)
        if not match or match.group(1)=='01': continue
        digest=x.get('computed_md5') or x.get('supplied_md5')
        if not isinstance(digest,str) or not re.fullmatch('[a-fA-F0-9]{32}',digest):
            continue
        if size<=0 or size>MAX_SINGLE_BYTES:continue
        key=int(match.group(1));cell=match.group(2)
        by_group[key].setdefault(cell,[]).append({'filename':name,'id':fid,'size_bytes':size,'publisher_md5':digest.lower()})
    candidates=[]
    for cohort,group in sorted(by_group.items()):
        if set(group)!={'4','5','6'} or any(len(group[x])!=1 for x in ('4','5','6')):continue
        total=sum(group[x][0]['size_bytes'] for x in ('4','5','6'))
        if total>MAX_COHORT_BYTES:continue
        candidates.append({'testpoint':f'TP_k{cohort:02d}',
                           'total_original_bytes':total,
                           'original_publisher_files':[group[x][0] for x in ('4','5','6')]})
    return {'schema':'cano.battery.publisher-new-cohort-metadata-preflight.v1',
            'publisher_article_id':25975315,'publisher_doi':meta['doi'],
            'publisher_metadata_sha256':raw_sha256,
            'source_files_listed':len(files),
            'publisher_duplicate_filename_count':sum(v>1 for v in name_counts.values()),
            'publisher_duplicate_filename_examples':sorted((k,v) for k,v in name_counts.items() if v>1)[:30],
            'source_cell_name_collision_cohorts':sum(set(g)=={'4','5','6'} and any(len(g[c])>1 for c in ('4','5','6')) for g in by_group.values()),
            'eligible_full_three_cell_cohorts':len(candidates),
            'eligible_cohorts':candidates,
            'chosen_cohort':candidates[0] if candidates else None,
            'already_studied_testpoint':'TP_k01',
            'next_source_zip_downloaded':False,'real_measurements_examined':0,
            'external_physical_identity_authenticated':False,
            'population_field_FPR_FNR_established':False,
            'decision':'NEW_SOURCE_COHORT_METADATA_FOUND' if candidates else 'NO_UNAMBIGUOUS_NEW_COHORT_WITHIN_BOUNDED_BUDGET'}


def main(argv=None):
    a=sys.argv[1:] if argv is None else argv
    if len(a)!=1:print('usage: preflight OUTPUT.json',file=sys.stderr);return 2
    target=Path(a[0]);
    if target.exists() or not target.parent.is_dir():print('REVIEW_REQUIRED: output exists',file=sys.stderr);return 2
    try:
        with urlopen(Request(API,headers={'User-Agent':'CANO-battery-source-next-cohort/1.0','Accept':'application/json'}),timeout=45) as r:
            parsed=urlparse(r.geturl());raw=r.read(MAX_METADATA_BYTES+1)
            if r.status!=200 or parsed.scheme!='https' or parsed.hostname!='api.figshare.com':
                raise ValueError('SOURCE_REVIEW_REQUIRED: publisher redirect')
        if len(raw)>MAX_METADATA_BYTES:raise ValueError('SOURCE_REVIEW_REQUIRED: oversized metadata')
        report=inspect_metadata(json.loads(raw),sha256(raw).hexdigest())
        target.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        print('PUBLISHER_ONLY_COHORT_PREFLIGHT',json.dumps({'eligible':report['eligible_full_three_cell_cohorts'],'selected':report['chosen_cohort']},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError) as e:
        print('SOURCE_REVIEW_REQUIRED:',str(e)[:200],file=sys.stderr);return 2
if __name__=='__main__':raise SystemExit(main())