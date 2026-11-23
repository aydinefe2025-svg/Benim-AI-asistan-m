#!/usr/bin/env python3
"""Source-pinned reproduction of published BIRDS solar-panel screening rules.

Paper: Jara Cespedes et al., Applied Sciences 12 (2022) 8634,
doi:10.3390/app12178634, Sec 3.1.1-3.1.2.
Screening rule != physical-fault adjudication. Preserve original rows.
No training/testing leakage, no SoH estimation, no cause inference.
"""
import base64
import collections
import datetime
import hashlib
import io
import json
import math
import posixpath
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from birds_eps_constellation_qc import (
    FIELDS_TSURU_14, NS, REL, SOURCES, SRC, colname, decode_cell, shared_strings,
)
from tsuru_agv_real_source_ci import GIT_SHA, get

# Explicit published engineering units: 5 panel voltage/current pairs.
PANEL_COLUMNS = {
    "PY": ("M", "W"), "PX": ("O", "Y"), "MZ": ("Q", "AA"),
    "MX": ("S", "AC"), "PZ": ("U", "AE"),
}
EXPECTED_VOLT_HEADERS = {
    "M": "Vpy (mV)", "O": "Vpx (mV)", "Q": "Vmz (mV)",
    "S": "Vmx (mV)", "U": "Vpz (mV)",
}
EXPECTED_CURRENT_HEADERS = {
    "W": "Ipy (mA)", "Y": "Ipx (mA)", "AA": "Imz (mA)",
    "AC": "Imx (mA)", "AE": "Ipz (mA)",
}
MISSING = object()
THRESHOLD_MV = 1200.0
LOW_WINDOW_MV = 2000.0
HIGH_WINDOW_MV = 3000.0
LOW_CURRENT_MA = 50.0
MAX_ADJACENT_SECONDS = 100.0  # 10 s fast, 90 s nominal sampling; gap-aware sensitivity

def panel_flags(series, max_gap_seconds=None):
    """Record-level alerts for a single original XLSX worksheet, NEVER across sheets.

    Each row: {'row': spreadsheet_row, 't': seconds, 'vals': column => finite float}.
    Explicitly compare source row indexes so missing records cannot join triplets.
    """
    votes = {"type1": set(), "type2": set()}
    details = {p: {"type1": 0, "type2": 0} for p in PANEL_COLUMNS}
    for i, entry in enumerate(series):
        vals = entry["vals"]
        for panel, (vcol, icol) in PANEL_COLUMNS.items():
            volt = vals[vcol]
            if volt < THRESHOLD_MV:
                votes["type1"].add(entry["row"])
                details[panel]["type1"] += 1
            if not (LOW_WINDOW_MV <= volt <= HIGH_WINDOW_MV and vals[icol] < LOW_CURRENT_MA):
                continue
            if i == 0 or i + 1 == len(series):
                continue
            a, b = series[i-1], series[i+1]
            # Sequential source observations, strictly increasing spacecraft timestamps.
            if (a["row"] + 1 != entry["row"] or entry["row"] + 1 != b["row"] or
                    not a["t"] < entry["t"] < b["t"]):
                continue
            if max_gap_seconds is not None and (
                entry["t"]-a["t"] > max_gap_seconds or b["t"]-entry["t"] > max_gap_seconds
            ):
                continue
            if all(LOW_WINDOW_MV <= x["vals"][vcol] <= HIGH_WINDOW_MV for x in (a,b)):
                votes["type2"].add(entry["row"])
                details[panel]["type2"] += 1
    return votes, details

def parse_one_workbook(raw, satellite, expected):
    assert len(raw) == expected["bytes"], "original file byte length differs"
    gid = hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    assert gid == expected["sha1"], "Git source identity mismatch"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None, "full original XLSX CRC failure"
        names = z.namelist()
        sheets = ET.fromstring(z.read("xl/workbook.xml")).findall(NS+"sheets/"+NS+"sheet")
        relationships = {e.get("Id"):e.get("Target") for e in
                         ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        strings=shared_strings(z)
        count=collections.Counter()
        by_sheet={}
        panel_counter={p:collections.Counter() for p in PANEL_COLUMNS}
        first_alarm={}  # first candidate in original timestamp units, no UTC inference
        for sh in sheets:
            label=sh.get("name")
            target=relationships[sh.get(REL+"id")]
            path=target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl",target))
            assert path in names and path.startswith("xl/worksheets/")
            doc=ET.fromstring(z.read(path))
            xml_rows=doc.findall(NS+"sheetData/"+NS+"row")
            is_test=label.startswith(("Test1","Test2")) if satellite=="TSURU" else False
            if not xml_rows:
                by_sheet[label]={"rows":0,"flight_evaluable_rows":0,"is_test":is_test}
                continue
            h={colname(c.get("r")):decode_cell(c,strings) for c in xml_rows[0].findall(NS+"c")}
            for col, expected_header in {**EXPECTED_VOLT_HEADERS,**EXPECTED_CURRENT_HEADERS}.items():
                assert str(h.get(col,"")).strip()==expected_header, (
                    "publisher voltage/current column mapping changed", satellite,label,col,h.get(col))
            series=[]
            prefix_open=True
            last_t=None
            raw_rows=max(0,len(xml_rows)-1)
            count["source_rows"]+=raw_rows
            for rr in xml_rows[1:]:
                rowid=int(rr.get("r"))
                values={}
                for c in rr.findall(NS+"c"):
                    col=colname(c.get("r"))
                    if col not in FIELDS_TSURU_14:
                        continue
                    val=decode_cell(c,strings)
                    if isinstance(val,float) and math.isfinite(val):
                        values[col]=val
                complete=all(col in values for col in FIELDS_TSURU_14)
                if complete:
                    count["complete_14_rows"]+=1
                if is_test:
                    count["explicit_test_rows"]+=1
                    continue
                if satellite=="TSURU":
                    # Preserve original conservative first monotone numeric prefix.
                    qualifies=(prefix_open and complete and
                               (last_t is None or values["A"]>last_t))
                    if not qualifies:
                        prefix_open=False
                    if not prefix_open:
                        count["flight_quarantined_suffix"]+=1
                        continue
                elif not complete:
                    count["flight_incomplete_rows"]+=1
                    continue
                if not complete:
                    continue
                series.append({"row":rowid,"t":values["A"],"vals":values})
                last_t=values["A"]
                count["flight_evaluable_rows"]+=1
            loose,per_loose=panel_flags(series)
            strict,per_strict=panel_flags(series,max_gap_seconds=MAX_ADJACENT_SECONDS)
            assert strict["type2"].issubset(loose["type2"]), "gap check inverted"
            for typ in ("type1","type2"):
                count[typ+"_loose_rows"]+=len(loose[typ])
                count[typ+"_strict_rows"]+=len(strict[typ])
            count["any_loose_rows"]+=len(loose["type1"]|loose["type2"])
            count["any_strict_rows"]+=len(strict["type1"]|strict["type2"])
            for pn in PANEL_COLUMNS:
                for typ in ("type1","type2"):
                    panel_counter[pn][typ+"_loose"]+=per_loose[pn][typ]
                    panel_counter[pn][typ+"_strict"]+=per_strict[pn][typ]
            for typ in ("type1","type2"):
                for row in series:
                    if row["row"] in strict[typ]:
                        key=pn if False else typ
                        if typ not in first_alarm:
                            first_alarm[typ]={"sheet":label,"source_row":row["row"],"time_A_seconds":row["t"]}
                        break
            by_sheet[label]={
                "source_data_rows":raw_rows,"flight_evaluable_rows":len(series),
                "is_test":is_test,
                "type1_rows":len(strict["type1"]),
                "type2_rows_consecutive_source":len(loose["type2"]),
                "type2_rows_gap_limited_100s":len(strict["type2"]),
                "any_screen_positive":len(strict["type1"]|strict["type2"]),
            }
        expected_count={"TSURU":(42,26023,24378,23266),
                        "UGUISU":(3,3270,3260,3260),
                        "RAAVANA":(2,2159,2159,2159),
                        "NEPALISAT":(3,3040,3040,3040)}
        es,er,ec,ee=expected_count[satellite]
        assert len(sheets)==es and count["source_rows"]==er, "source structure changed"
        assert count["complete_14_rows"]==ec and count["flight_evaluable_rows"]==ee, (
            "numeric profile differs from verified independent baseline", satellite,dict(count))
        if satellite=="TSURU":
            assert count["flight_quarantined_suffix"]==1645
            assert count["explicit_test_rows"]==1112
        if satellite=="UGUISU":
            assert count["flight_incomplete_rows"]==10
        return {
            "blob_sha1":gid,"sha256":hashlib.sha256(raw).hexdigest(),
            "source_bytes":len(raw),"sheets":len(sheets),
            "counts":dict(count),"panel_counts":{p:dict(v) for p,v in panel_counter.items()},
            "first_screening_hits_source_clock_not_utc":first_alarm,"sheets_profile":by_sheet,
        }

def main():
    original_receipts=json.loads(Path("BIRDS_FOUR_EPS_CI_RECEIPT.json").read_text())
    assert original_receipts["status"]=="FOUR_SATELLITE_SOURCE_IDENTITIES_AND_OOXML_PROFILE_VERIFIED"
    satellites={}
    for satellite, pin in [
        ("TSURU",{"sha1":GIT_SHA,"bytes":6059029}),
        *sorted(SOURCES.items()),
    ]:
        document=json.loads(get(SRC+pin["sha1"],github=True))
        assert document["sha"]==pin["sha1"] and document["encoding"]=="base64"
        raw=base64.b64decode("".join(document["content"].split()),validate=True)
        satellites[satellite]=parse_one_workbook(raw,satellite,pin)
        print("BIRDS_PUBLISHED_SCREEN_REAL="+json.dumps({
            "satellite":satellite,"rows":satellites[satellite]["counts"]["flight_evaluable_rows"],
            "type1":satellites[satellite]["counts"].get("type1_strict_rows",0),
            "type2":satellites[satellite]["counts"].get("type2_strict_rows",0)
        }))
    receipt={
        "status":"PUBLISHER_RULES_APPLIED_TO_PINNED_SOURCE_SCREENING_ONLY",
        "generated_at_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "literature":"https://doi.org/10.3390/app12178634 sec 3.1.1-3.1.2",
        "source":"https://github.com/BIRDSOpenSource/EPS_dataset",
        "rule_type1":"any selected panel voltage reading below 1200 mV",
        "rule_type2":"same panel voltage 2000..3000 mV on preceding/center/following consecutive source rows AND center-panel current below 50 mA; also require timestamps strictly increasing",
        "time_gap_sensitivity_seconds":MAX_ADJACENT_SECONDS,
        "source_clock_not_wall_time":True,
        "independent_physical_fault_confirmation":False,
        "limitations":[
            "These are candidate anomaly-screening flags, not confirmed independent panel or solar-cell hardware failure.",
            "Type 1 original paper threshold may be operationally calibrated by its mission team, not independently validated here.",
            "Type 2 gaps, eclipse illumination, attitude and temporal dependence cannot be fully adjudicated from this audit.",
            "Source data lacks independent physical field intervention or calibration provenance for new failure-time claims.",
        ],
        "satellites":satellites,
    }
    Path("BIRDS_FOUR_PUBLISHED_PANEL_RULES_SCREEN_RECEIPT.json").write_text(
        json.dumps(receipt,indent=2,sort_keys=True)+"\n")
if __name__=="__main__":
    main()
