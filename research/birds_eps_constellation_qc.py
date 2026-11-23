#!/usr/bin/env python3
"""Verify the other three original BIRDS EPS workbooks (observational data audit).

Uses immutable upstream Git blob IDs. No physical-fault / battery-health
assertion, and no inferred equivalence between measurement fields.
"""
import base64
import collections
import datetime
import hashlib
import io
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from tsuru_agv_real_source_ci import get

SRC = "https://api.github.com/repos/BIRDSOpenSource/EPS_dataset/git/blobs/"
SOURCES = {
    "UGUISU": {"sha1": "d230734c0955776bbe0abcda12c6f5d87eb940c1", "bytes": 737659},
    "RAAVANA": {"sha1": "f0bc233f8e7d5f5b9585c3fb8c794486132cb111", "bytes": 485809},
    "NEPALISAT": {"sha1": "8128db6a60f9058976c1147f3d6ade690dbfea17", "bytes": 745668},
}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
FIELDS_TSURU_14 = ("A","AG","AI","AK","M","O","Q","S","U","W","Y","AA","AC","AE")


def colname(cellref):
    m = re.fullmatch(r"([A-Z]+)[0-9]+", cellref or "")
    return m.group(1) if m else None


def shared_strings(z):
    if "xl/sharedStrings.xml" not in z.namelist():
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.iter(NS+"t")) for si in root.findall(NS+"si")]


def decode_cell(c, strings):
    value = c.find(NS+"v")
    kind = c.get("t", "n")
    if kind == "inlineStr":
        node = c.find(NS+"is")
        return "".join(t.text or "" for t in node.iter(NS+"t")) if node is not None else ""
    if value is None or value.text is None:
        return None
    if kind == "s":
        return strings[int(value.text)]
    if kind in ("str", "e", "b"):
        return value.text
    try:
        return float(value.text)
    except (ValueError, OverflowError):
        return value.text


def workbook_profile(raw, source):
    # Complete bit identity check prevents silently following a mutable file.
    assert len(raw) == source["bytes"], "source byte length unexpectedly changed"
    git_sha = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
    assert git_sha == source["sha1"], "source original Git blob SHA-1 mismatch"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        assert len(set(names)) == len(names), "duplicate source OOXML member names"
        assert z.testzip() is None, "OOXML member CRC failed"
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        relations = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        links = {e.get("Id"):e.get("Target") for e in relations}
        sheets = wb.findall(NS+"sheets/"+NS+"sheet")
        assert sheets, "missing workbook sheets"
        shared = shared_strings(z)
        profiles = []
        for sheet in sheets:
            label = sheet.get("name", "")
            target = links[sheet.get(REL+"id")]
            path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl",target))
            assert path.startswith("xl/worksheets/") and path in names, path
            xml = ET.fromstring(z.read(path))
            rows = xml.findall(NS+"sheetData/"+NS+"row")
            if not rows:
                profiles.append({"sheet":label,"xml_rows":0,"data_rows_after_first":0,"numeric_14field_rows":0,"time_A_nonincreasing_pairs":0})
                continue
            first = rows[0]
            header = {}
            for cell in first.findall(NS+"c"):
                col = colname(cell.get("r"))
                if col:
                    value = decode_cell(cell, shared)
                    header[col] = str(value)[:100] if value is not None else None
            full14 = 0
            time_rows = 0
            backwards = []
            prev_time = None
            numeric_rows = 0
            nonfinite_numeric_cells = 0
            nonempty = 0
            for rr in rows[1:]:
                nums={}
                for cell in rr.findall(NS+"c"):
                    col=colname(cell.get("r"))
                    if not col:
                        continue
                    val=decode_cell(cell, shared)
                    if val is not None:
                        nonempty+=1
                    if isinstance(val,float):
                        if not (val == val and abs(val) != float("inf")):
                            nonfinite_numeric_cells+=1
                        else:
                            nums[col]=val
                if nums:
                    numeric_rows+=1
                if all(col in nums for col in FIELDS_TSURU_14):
                    full14+=1
                timestamp=nums.get("A")
                if timestamp is not None:
                    time_rows+=1
                    if prev_time is not None and timestamp<=prev_time:
                        backwards.append({"xml_row":rr.get("r"),"previous_A":prev_time,"current_A":timestamp})
                    prev_time=timestamp
            profiles.append({
                "sheet":label,"xml_rows":len(rows),"data_rows_after_first":max(0,len(rows)-1),
                "numeric_data_rows":numeric_rows,"numeric_14field_rows":full14,
                "numeric_time_A_rows":time_rows,"time_A_nonincreasing_pairs":len(backwards),
                "time_A_first_resets":backwards[:5], "nonfinite_numeric_cells":nonfinite_numeric_cells,
                "header_first_row":header, "nonempty_cell_count":nonempty,
            })
    return {
        "source_size":len(raw),"git_blob_sha1":git_sha,"sha256":hashlib.sha256(raw).hexdigest(),
        "crc_pass_all_members":len(names),"sheet_count":len(profiles),
        "xml_rows":sum(p["xml_rows"] for p in profiles),
        "rows_after_first_total":sum(p["data_rows_after_first"] for p in profiles),
        "numeric_data_rows":sum(p["numeric_data_rows"] for p in profiles),
        "numeric_14field_rows":sum(p["numeric_14field_rows"] for p in profiles),
        "numeric_time_A_rows":sum(p["numeric_time_A_rows"] for p in profiles),
        "time_A_nonincreasing_pairs":sum(p["time_A_nonincreasing_pairs"] for p in profiles),
        "time_A_sheets_with_resets":sum(p["time_A_nonincreasing_pairs"]>0 for p in profiles),
        "sheet_details":profiles,
        "measurement_interpretation":"Exploratory source morphology. A is not certified as time for all sheets, and the TSURU 14-column model is NOT assumed to be valid for other satellites.",
    }


def main():
    receipt_file=Path("TSURU_AGV_REAL_SOURCE_CI_RECEIPT.json")
    assert receipt_file.exists(), "TSURU/AGV original real CI prerequisite absent"
    prior=json.loads(receipt_file.read_text())
    assert prior["status"]=="BOTH_ORIGINAL_BYTES_REPLAYED_AND_PINNED"
    assert prior["tsuru"]["git_blob_sha1"]=="4bdb9770300050a33e86ff41b6c9a35d13b565e9"
    assert prior["tsuru"]["numeric_time_qc"]["complete_numeric_rows"]==24378
    satellites={"TSURU":{"sha256":prior["tsuru"]["sha256"],"status":"original_verified_in_existing_tsuru_agv_replay"}}
    for name, pin in SOURCES.items():
        response=json.loads(get(SRC+pin["sha1"], github=True))
        assert response["sha"]==pin["sha1"] and response["encoding"]=="base64"
        raw=base64.b64decode(response["content"],validate=True)
        satellites[name]=workbook_profile(raw,pin)
        print("EPS_SOURCE_VERIFIED="+json.dumps({"satellite":name,"bytes":len(raw),
                "sheets":satellites[name]["sheet_count"],
                "rows_after_first":satellites[name]["rows_after_first_total"],
                "all_zip_member_crc":satellites[name]["crc_pass_all_members"],
                "raw_14field_rows":satellites[name]["numeric_14field_rows"],
                "A_nonincreasing":satellites[name]["time_A_nonincreasing_pairs"]}))
    assert len(satellites)==4
    out={
        "status":"FOUR_SATELLITE_SOURCE_IDENTITIES_AND_OOXML_PROFILE_VERIFIED",
        "run_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "origin_repository":"https://github.com/BIRDSOpenSource/EPS_dataset",
        "source_license":"MIT, Kyushu Institute of Technology (2022); no source binary redistributed",
        "satellites":satellites,
        "agv":{"status":"original_verified_in_existing_tsuru_agv_replay","source_md5":prior["agv"]["md5"],"rows":prior["agv"]["rows"]},
        "claims_not_established":["flight-qualified instrumentation calibration", "fault onset time", "causal solar panel failure diagnosis", "battery state of health", "satellite cross-comparison from unaligned units"],
    }
    Path("BIRDS_FOUR_EPS_CI_RECEIPT.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
