"""Reproducible original 3-cell / 3-temperature ET-AT capacity audit.

Runs on immutable publisher-verified Figshare ZIPs, either live HTTPS or
already preserved OFFLINE originals. Uses the authors' step 21+22 current-time
method; no capacity comparisons between different temperatures as equivalent
protocols, no independent physical custody or field FPR/FNR claims.
"""
from __future__ import annotations
from pathlib import Path, PurePosixPath
from hashlib import sha256
import json
import re
import sys
import io
from zipfile import ZipFile

from research.battery_curve_audit.figshare_three_archive_probe import (
    URL, PINNED, MAX_META_BYTES, MAX_SOURCE_BYTES,
    fetch_bounded, inspect_zip, validate_source_meta
)
from research.battery_curve_audit.figshare_k01_et_at_capacity import (
    inspect_phase, _meta_record
)
from research.battery_curve_audit.figshare_identity_provenance import (
    summarize_meta_sidecar,
)

TEMPERATURE_C = (10,23,45)
EXPECTED_POINT = "k01nocu"
AUTHOR_METHOD_BLOB = "e6d699223a1df79bf10869f608951c32a0e66c15"
SOURCE_DOI = "10.6084/m9.figshare.25975315"


def analyze_cell(z: ZipFile, stem: str) -> list[dict]:
    """Reject missing/ambiguous original measurements and conflicting sidecars."""
    if not re.fullmatch(r"TP_k01_0[456]",stem):
        raise ValueError("SOURCE_REVIEW_REQUIRED: unexpected original stage/testpoint")
    names=z.namelist()
    if len(set(names))!=len(names):
        raise ValueError("SOURCE_REVIEW_REQUIRED: duplicate archive member")
    known_identity=None
    profiles=[]
    for temp in TEMPERATURE_C:
        sides={}
        measures={}
        for phase in ("ET","AT"):
            pattern=re.compile(re.escape(stem)+r"_\d{2}_"+phase+r"_T"+str(temp)+r"\.csv$")
            choices=[n for n in names if pattern.fullmatch(PurePosixPath(n).name)]
            if len(choices)!=1:
                raise ValueError("SOURCE_REVIEW_REQUIRED: missing or ambiguous original ET/AT temperature file")
            name=choices[0]
            src=_meta_record(z,name)
            metaname=name[:-4]+"_meta.txt"
            extras=summarize_meta_sidecar(z.read(metaname))["parsed_fields"]
            point=str(extras.get("testpoint") or "").strip().casefold()
            if point!=EXPECTED_POINT:
                raise ValueError("SOURCE_REVIEW_REQUIRED: publisher calendar noCU testpoint label mismatch")
            degree=src["temperature"]
            if degree is None or degree.strip().replace(" ","")!=str(temp)+"°C":
                raise ValueError("SOURCE_REVIEW_REQUIRED: original chamber-temperature mismatch")
            identity=(src["lab"],src["serial"],point)
            if known_identity is None: known_identity=identity
            if identity!=known_identity:
                raise ValueError("SOURCE_REVIEW_REQUIRED: lab / original cell serial changed across temperature or phase")
            sides[phase]={"meta_sha256":src["paired_meta_sha256"],
                          "source_name":PurePosixPath(name).name}
            measures[phase]=inspect_phase(z,name)
        et=measures["ET"];at=measures["AT"]
        if not et["source_capacity_extractable"] or not at["source_capacity_extractable"]:
            raise ValueError("SOURCE_REVIEW_REQUIRED: original capacity phase missing or uncertain")
        et_q=et["capacity_mean_Ah"];at_q=at["capacity_mean_Ah"]
        profiles.append({
            "temperature_C":temp,
            "et_source_name":sides["ET"]["source_name"],
            "at_source_name":sides["AT"]["source_name"],
            "et_sidecar_sha256":sides["ET"]["meta_sha256"],
            "at_sidecar_sha256":sides["AT"]["meta_sha256"],
            "et_rows":et["source_rows_processed"],
            "at_rows":at["source_rows_processed"],
            "et_capacity_Ah":et_q,
            "at_capacity_Ah":at_q,
            "et_to_at_change_percent":round(100*(at_q/et_q-1),4),
            "original_step21_and_step22_valid_both_phases":True,
            "source_sidecar_identity_matched":True,
            "measurement_source_temperature_matched":True,
            "physical_identity_independently_authenticated":False,
            "storage_only_aging_attribution_proved":False,
        })
    return profiles


def run(offline_dir: Path|None=None)->dict:
    """Offline mode reads saved original ZIPs without network or extra purchases."""
    if offline_dir is None:
        api=fetch_bounded(URL,MAX_META_BYTES)
        publisher=json.loads(api)
        expected=validate_source_meta(publisher)
        metadata_sha=sha256(api).hexdigest()
    else:
        if not offline_dir.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: no offline source directory")
        expected=[{"id":fid,"name":name,"size":size,"md5":digest}
                  for fid,name,size,digest in PINNED]
        metadata_sha=None
    cells=[]
    for original in expected:
        if offline_dir is None:
            raw=fetch_bounded(
                "https://ndownloader.figshare.com/files/"+str(original["id"]),
                MAX_SOURCE_BYTES)
        else:
            path=offline_dir/original["name"]
            if path.is_symlink() or not path.is_file() or path.stat().st_size!=original["size"]:
                raise ValueError("SOURCE_REVIEW_REQUIRED: offline original source file missing/changed")
            raw=path.read_bytes()
        proof=inspect_zip(raw,original)
        with ZipFile(io.BytesIO(raw)) as z:
            profiles=analyze_cell(z,original["name"][:-4])
        cells.append({
            "publisher_file_id":original["id"],
            "publisher_original_filename":original["name"],
            "original_size_bytes":len(raw),
            "original_sha256":proof["original_zip_sha256"],
            "publisher_md5_verified":proof["publisher_md5_matched"],
            "original_crc_verified":proof["zip_crc_passed"],
            "all_six_original_measurements_source_matched":True,
            "source_profiles":profiles,
        })
    all_profiles=[p for c in cells for p in c["source_profiles"]]
    return {
        "schema":"cano.battery.figshare279.original-k01-3cell-3temp-et-at-capacity.v1",
        "source_doi":SOURCE_DOI,
        "publisher_metadata_sha256":metadata_sha,
        "publisher_api_queried_this_run":offline_dir is None,
        "original_author_method_git_blob_sha":AUTHOR_METHOD_BLOB,
        "publisher_license":"CC BY 4.0",
        "source_archives":cells,
        "original_archives_verified":len(cells),
        "original_csv_files_processed":len(all_profiles)*2,
        "source_capacity_pair_count":len(all_profiles),
        "original_timestamp_voltage_current_rows_processed":
          sum(p["et_rows"]+p["at_rows"] for p in all_profiles),
        "all_capacity_pairs_current_time_and_sidecar_validated":True,
        "source_testpoint_04_05_06_has_no_intermediate_CU":"k01noCU",
        "storage_only_aging_attribution_proven":False,
        "external_physical_cell_custody_authenticated":False,
        "field_FPR_FNR_established":False,
        "commercial_release_allowed":False,
        "decision":"ORIGINAL_3CELL_3TEMP_ET_AT_MEASURED_RESEARCH_ONLY",
    }


def main(argv=None)->int:
    args=list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) not in (1,3) or (len(args)==3 and args[1]!="--offline-originals"):
            raise ValueError("usage: python -m research.battery_curve_audit.figshare_k01_three_temperatures OUTPUT.json [--offline-originals ZIP_DIRECTORY]")
        target=Path(args[0])
        if target.exists() or not target.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: report path exists or parent missing")
        offline=Path(args[2]) if len(args)==3 else None
        result=run(offline)
        with target.open("x",encoding="utf-8") as fh:
            json.dump(result,fh,indent=2,sort_keys=True)
            fh.write("\n")
        print(json.dumps({
            "decision":result["decision"],
            "original_csv_files_processed":result["original_csv_files_processed"],
            "original_rows":result["original_timestamp_voltage_current_rows_processed"],
            "cells":[{"original_id":c["publisher_file_id"],
                     "capacity_pct":[p["et_to_at_change_percent"] for p in c["source_profiles"]]}
                    for c in result["source_archives"]]},sort_keys=True))
        return 0
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print("SOURCE_REVIEW_REQUIRED:",str(exc)[:180],file=sys.stderr)
        return 2


if __name__=="__main__":
    raise SystemExit(main())
