"""Bounded audit: original Zenodo README provenance + original-source-derived EIS strata.

The two filename strata are *not* labeled by impacter diameter without
publisher-explicit individual specimen-to-geometry evidence. No field release.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import statistics
import sys
import urllib.request

RECORD = 18213931
DOI = '10.5281/zenodo.18213931'
README_NAME = 'ReadME.txt'
README_MD5 = 'ab962466161226203b94d2724d2b68e0'
LEDGER_SHA = 'c17a5b340a892db990fdc910e501df8a17c7e990ef723d309206dc4952f78953'
PARENT_ARTIFACT_SHA = '44f70afbdf1b0e0e8bb7af0599ff46c60e9b1514baaa4cf5e5f83faa5d04ad43'
IDS_A = tuple(f'EIS_C{n:02d}.xlsx' for n in range(2,7))
IDS_B = tuple(f'EIS_C{n:02d}.xlsx' for n in range(9,14))
LEVELS = ('0% deformation','25% deformation','50% deformation','75% deformation','95% deformation')
METRICS = ('spectral_median_pct','freq_10_033Hz','freq_1035_2Hz')


def get_bytes(url: str, limit: int)->bytes:
    if not isinstance(url,str) or not url.startswith('https://zenodo.org/') or limit<=0:
        raise ValueError('SOURCE_NOT_TRUSTED: unsupported URL')
    req=urllib.request.Request(url,headers={'User-Agent':'CANO public independent source verifier/1.0'})
    with urllib.request.urlopen(req, timeout=35) as resp:
        if resp.status!=200:raise ValueError('SOURCE_REVIEW_REQUIRED: non-200')
        blob=resp.read(limit+1)
    if not (0<len(blob)<=limit):raise ValueError('SOURCE_REVIEW_REQUIRED: size limit')
    return blob


def parse_readme_published_impactor_mapping(source_text: str)->dict:
    """Accept only explicit original publisher Cxx ranges and diameters, never EIS signs.

    This verifies *source-documented specimen labels*, NOT independent human
    chain-of-custody or external mechanical geometry calibration.
    """
    if not isinstance(source_text,str):
        raise ValueError('SOURCE_REVIEW_REQUIRED: invalid original README text')
    lines=[ln.strip() for ln in source_text.splitlines() if ln.strip()]
    accepted={
        'Cell 02-06: hemispherical impactor d= 30 mm':('C02','C03','C04','C05','C06',30),
        'Cell 09-13: hemispherical impactor d= 180 mm':('C09','C10','C11','C12','C13',180),
    }
    # A source document that contradicts the expected mappings, includes
    # duplicate diameter lines, or changes specimen identities cannot pass.
    geometry_lines=[ln for ln in lines if 'hemispherical impactor' in ln.lower()]
    if len(geometry_lines)!=2 or set(geometry_lines)!=set(accepted):
        raise ValueError('SOURCE_REVIEW_REQUIRED: missing/contradictory individual source diameter mapping')
    return {
        'publisher_documented_groups':[
            {'original_specimen_ids':list(v[:5]),'indenter_diameter_mm':v[5]}
            for v in accepted.values()
        ],
        'original_publisher_readme_mapping_verified':True,
        'independent_physical_custody_witness_verified':False,
        'independent_mechanical_diameter_calibration_verified':False,
    }


def verify_original_readme(metadata:dict, raw:bytes)->dict:
    if not isinstance(metadata,dict) or type(metadata.get('id')) is not int or metadata['id']!=RECORD:
        raise ValueError('SOURCE_REVIEW_REQUIRED: wrong Zenodo record')
    files=metadata.get('files')
    if not isinstance(files,list) or len(files)<11:raise ValueError('SOURCE_REVIEW_REQUIRED: incomplete index')
    same=[f for f in files if f.get('key')==README_NAME]
    if len(same)!=1 or same[0].get('checksum')!='md5:'+README_MD5:
        raise ValueError('SOURCE_REVIEW_REQUIRED: README checksum metadata mismatch')
    if not isinstance(raw,bytes) or len(raw)>3000 or hashlib.md5(raw).hexdigest()!=README_MD5:
        raise ValueError('SOURCE_REVIEW_REQUIRED: README original bytes mismatch')
    try: source_text=raw.decode('utf-8-sig')
    except UnicodeDecodeError as ex:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid README encoding') from ex
    if any(ord(ch)<32 and ch not in '\n\r\t' for ch in source_text):
        raise ValueError('SOURCE_REVIEW_REQUIRED: control characters in README')
    # This is the **actual original publisher source text** after MD5 verification.
    # Its explicit 02-06 and 09-13 mapping, not the sign of EIS, authorizes labels.
    documented=parse_readme_published_impactor_mapping(source_text)
    return {'record':RECORD,'source_readme_filename':README_NAME,'publisher_md5_verified':True,
            'md5':README_MD5,'sha256':hashlib.sha256(raw).hexdigest(),'readme_text':source_text,
            **documented, 'not_equivalent_to_calibration':True}


def read_ledger(blob:bytes)->dict:
    if not isinstance(blob,bytes):
        raise ValueError('SOURCE_REVIEW_REQUIRED: untrusted ledger type')
    # Windows Git checkouts can replace LF with CRLF; allow ONLY that reversible
    # line-ending conversion, then still enforce the immutable original digest.
    canonical=blob if hashlib.sha256(blob).hexdigest()==LEDGER_SHA else blob.replace(b'\r\n',b'\n')
    if hashlib.sha256(canonical).hexdigest()!=LEDGER_SHA:
        raise ValueError('SOURCE_REVIEW_REQUIRED: prior source-derived ledger SHA changed')
    try: doc=json.loads(canonical)
    except (ValueError,UnicodeDecodeError) as e:raise ValueError('SOURCE_REVIEW_REQUIRED: invalid ledger') from e
    if doc.get('source_artifact_sha256')!=PARENT_ARTIFACT_SHA or doc.get('source_doi')!=DOI:
        raise ValueError('SOURCE_REVIEW_REQUIRED: ledger source detached')
    cells=doc.get('cells')
    if not isinstance(cells,list) or len(cells)!=10 or {c.get('filename') for c in cells}!=set(IDS_A+IDS_B):
        raise ValueError('SOURCE_REVIEW_REQUIRED: distinct physical sample IDs missing')
    for c in cells:
        if not re.fullmatch('[a-f0-9]{64}',c.get('sha256','')):raise ValueError('SOURCE_REVIEW_REQUIRED: original SHA missing')
        stages=c.get('stages')
        if not isinstance(stages,list) or [s.get('level') for s in stages]!=list(LEVELS):
            raise ValueError('SOURCE_REVIEW_REQUIRED: stage lineage')
        for s in stages:
            if type(s.get('spectrum_rows')) is not int or s['spectrum_rows']!=101:
                raise ValueError('SOURCE_REVIEW_REQUIRED: original frequency grain')
            for metric in METRICS:
                val=s.get(metric)
                if type(val) not in (int,float) or not math.isfinite(val) or abs(val)>10000:
                    raise ValueError('SOURCE_REVIEW_REQUIRED: invalid raw-source-derived metric')
    return doc


def exact_partition_sensitivity(values: dict[str,float])->dict:
    if set(values)!=set(IDS_A+IDS_B) or any(type(v) not in (float,int) or not math.isfinite(v) for v in values.values()):
        raise ValueError('untrusted source stratum values')
    universe=sorted(values)
    a=statistics.median(values[k] for k in IDS_A)
    b=statistics.median(values[k] for k in IDS_B)
    delta=b-a
    tail=0
    for a_set in itertools.combinations(universe,5):
        b_set=set(universe)-set(a_set)
        d=statistics.median(values[k] for k in b_set)-statistics.median(values[k] for k in a_set)
        if abs(d)+1e-11>=abs(delta):tail+=1
    return {'stratum_A_median_pct':round(a,6),'stratum_B_median_pct':round(b,6),
        'difference_B_minus_A_pp':round(delta,6),'possible_label_partitions':252,
        'two_sided_complete_label_permutation_sensitivity':round(tail/252,8),
        'observed_tail_partitions':tail,
        'permutation_exchangeability_not_verified':True,
        'multiple_comparisons_exploratory':True}


def analyse_ledger(doc:dict)->dict:
    lookup={c['filename']:c for c in doc['cells']}
    result=[]
    for stage_idx,stage in enumerate(LEVELS[1:],1):
        for metric in METRICS:
            values={k:lookup[k]['stages'][stage_idx][metric] for k in sorted(lookup)}
            result.append({'stage':stage,'measurement':metric,**exact_partition_sensitivity(values)})
    return {'schema':'cano.battery.graz-eis-geometry-source-strata-v1',
        'source_doi':DOI,'prior_github_original_artifact_sha256':PARENT_ARTIFACT_SHA,
        'source_derived_ledger_sha256':LEDGER_SHA,'source_cells_analysed':10,
        'stratum_A_ids':[x[:-5] for x in IDS_A],
        'stratum_B_ids':[x[:-5] for x in IDS_B],
        'results':result,'comparisons_exploratory':True,
        'physical_diameter_assignment_verified':False,
        'physical_causation_established':False,'capacity_change_measured':False,
        'real_instrument_calibration_verified':False,'production_release_allowed':False}


def real_readme()->dict:
    metadata=json.loads(get_bytes(f'https://zenodo.org/api/records/{RECORD}',500000))
    entries=[e for e in metadata.get('files',[]) if e.get('key')==README_NAME]
    if len(entries)!=1:raise ValueError('SOURCE_REVIEW_REQUIRED: duplicate/absent readme')
    url=entries[0].get('links',{}).get('self','')
    raw=get_bytes(url,3000)
    return verify_original_readme(metadata,raw)


def run(ledger_path:Path, output_path:Path)->dict:
    ledger=read_ledger(ledger_path.read_bytes())
    readme=real_readme()
    source_strata=analyse_ledger(ledger)
    if not readme['original_publisher_readme_mapping_verified']:
        raise ValueError('SOURCE_REVIEW_REQUIRED: published specimen mapping missing')
    record={'source_readme':readme, 'source_derived_strata':source_strata,
        'geometry_comparison_valid_as_publisher_documented_groups':True,
        '30mm_original_specimens':list(x[:-5] for x in IDS_A),
        '180mm_original_specimens':list(x[:-5] for x in IDS_B),
        'independent_physical_custody_witness_verified':False,
        'mechanical_safety_certification':False,'physical_causality_established':False,
        'production_release_allowed':False}
    # Earlier ledger cannot authenticate geometry in isolation.
    assert source_strata['physical_diameter_assignment_verified'] is False
    assert readme['independent_physical_custody_witness_verified'] is False
    output_path.write_text(json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    return record


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=2:return 2
    try:
        out=Path(args[1]);src=Path(args[0])
        if out.exists() or not out.parent.is_dir():raise ValueError('SOURCE_REVIEW_REQUIRED: output exists/parent absent')
        doc=run(src,out)
        print('GRAZ_ZENODO_README_MD5_PASS',doc['source_readme']['readme_text'])
        print('GRAZ_ORIGINAL_PUBLISHER_DOCUMENTED_GEOMETRY_MAPPING',doc['source_readme']['publisher_documented_groups'])
        print('GRAZ_INDEPENDENT_PHYSICAL_CUSTODY_WITNESS',doc['independent_physical_custody_witness_verified'])
        for r in doc['source_derived_strata']['results']:
            if r['stage']=='95% deformation':print('GRAZ_95_SOURCE_STRATA',r)
        return 0
    except (ValueError,OSError,KeyError,TypeError,UnicodeError) as e:
        print('SOURCE_REVIEW_REQUIRED',str(e)[:160],file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
