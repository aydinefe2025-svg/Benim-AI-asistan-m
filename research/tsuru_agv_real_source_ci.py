#!/usr/bin/env python3
"""Real original-source replay in GitHub Actions; observational QC, no fault or SoH inference."""
import base64, collections, csv, datetime, hashlib, io, json, os, statistics, time
import urllib.request, xml.etree.ElementTree as ET, zipfile
from pathlib import Path

GIT_SHA = "4bdb9770300050a33e86ff41b6c9a35d13b565e9"
GIT_URL = "https://api.github.com/repos/BIRDSOpenSource/EPS_dataset/git/blobs/" + GIT_SHA
AGV_URLS = [
    "https://zenodo.org/api/records/7748947/files/dataset.csv/content",
    "https://zenodo.org/records/7748947/files/dataset.csv?download=1",
]
MD5_AGV = "2faa82bd0c27763d4b12d4c58510a1f5"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def get(url, github=False):
    headers = {"User-Agent": "CANO-raw-replay-evidence/1.0", "Accept": "application/json" if github else "*/*"}
    if github and os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = "Bearer " + os.environ["GITHUB_TOKEN"]
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=75) as r:
                return r.read()
        except Exception as exc:
            last = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError("publisher fetch failed: " + str(last))


def check_tsuru():
    b = json.loads(get(GIT_URL, github=True))
    assert b.get("sha") == GIT_SHA and b.get("encoding") == "base64"
    raw = base64.b64decode(b["content"])
    assert len(raw) == 6059029
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + bytes([0]) + raw).hexdigest()
    assert blob == GIT_SHA, "TSURU original Git blob SHA mismatch"
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members = z.namelist()
        assert len(members) == 70
        assert z.testzip() is None, "TSURU full ZIP CRC failed"
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        labels = [e.get("name") for e in wb.findall(NS + "sheets/" + NS + "sheet")]
        assert len(labels) == 42 and {"Test1 w batt", "Test2 wo batt"}.issubset(labels)
        files = sorted(n for n in members if n.startswith("xl/worksheets/sheet") and n.endswith(".xml"))
        assert len(files) == 42
        source_rows = sum(max(len(ET.fromstring(z.read(name)).findall(NS + "sheetData/" + NS + "row")) - 1, 0) for name in files)
        assert source_rows == 26023, f"TSURU rows changed: {source_rows}"
        timeseries = inspect_tsuru_timeseries(z)
    return {"bytes": len(raw), "numeric_time_qc": timeseries, "git_blob_sha1": blob, "sha256": hashlib.sha256(raw).hexdigest(),
            "zip_members_full_crc_pass": len(members), "sheets": len(labels),
            "rows_excluding_headers": source_rows, "two_test_sheets_explicit": True}



def inspect_tsuru_timeseries(z):
    """Full original numeric QC; conservative prefixes, no spacecraft-fault inference."""
    import posixpath
    import re
    R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
    fields = ("A", "AG", "AI", "AK", "M", "O", "Q", "S", "U", "W", "Y", "AA", "AC", "AE")
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    links = {e.get("Id"): e.get("Target") for e in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
    totals = collections.Counter()
    review_sheets = 0
    sample = {}
    per_sheet = {}
    for sheet in wb.findall(NS + "sheets/" + NS + "sheet"):
        label = sheet.get("name")
        target = links[sheet.get(R + "id")]
        path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
        assert path.startswith("xl/worksheets/"), path
        sheet_rows = ET.fromstring(z.read(path)).findall(NS + "sheetData/" + NS + "row")
        flight = not label.startswith(("Test1", "Test2"))
        n = 0
        sheet_complete = 0
        first_prefix = 0
        last_time = None
        for xml_row in sheet_rows[1:]:
            values = {}
            for c in xml_row.findall(NS + "c"):
                m = re.match(r"([A-Z]+)\d+$", c.get("r", ""))
                if not m or m.group(1) not in fields or c.get("t") in ("s", "str", "inlineStr"):
                    continue
                v = c.find(NS + "v")
                if v is None or v.text is None:
                    continue
                try:
                    values[m.group(1)] = float(v.text)
                except ValueError:
                    pass
            n += 1
            complete = all(a in values for a in fields)
            totals["complete_numeric_rows"] += int(complete)
            sheet_complete += int(complete)
            if flight:
                totals["flight_rows"] += 1
                if first_prefix == n - 1 and complete and (n == 1 or (last_time is not None and values["A"] > last_time)):
                    first_prefix += 1
                if label == "August 26" and values.get("AG") == 0:
                    sample["aug26_zero_volt_rows"] = sample.get("aug26_zero_volt_rows", 0) + 1
                if label == "August 26" and not complete:
                    sample["aug26_incomplete_rows"] = sample.get("aug26_incomplete_rows", 0) + 1
            last_time = values.get("A")
        per_sheet[label] = {"raw_rows":n, "complete":sheet_complete, "prefix":first_prefix}
        if flight:
            totals["flight_prefix_rows"] += first_prefix
            totals["flight_review_suffix_rows"] += n - first_prefix
            review_sheets += int(n != first_prefix)
            if label in ("August 26", "November 16", "December 20", "April 20"):
                sample[label + "_prefix"] = first_prefix
                sample[label + "_review_suffix"] = n - first_prefix
        else:
            totals["test_rows"] += n
    expected = {"complete_numeric_rows":25653, "flight_rows":24911, "flight_prefix_rows":23266, "flight_review_suffix_rows":1645, "test_rows":1112}
    observed = dict(totals)
    print("TSURU_DEEP_QC_DIAGNOSTIC=" + json.dumps({"totals": observed, "review_sheets": review_sheets, "sample": sample, "per_sheet": per_sheet}, sort_keys=True))
    for key, value in expected.items():
        assert observed.get(key) == value, "TSURU original numeric QC mismatch " + key + ": " + repr(observed.get(key))
    assert review_sheets == 14
    assert sample["August 26_prefix"] == 595 and sample["August 26_review_suffix"] == 921
    assert sample["November 16_prefix"] == 595 and sample["November 16_review_suffix"] == 536
    assert sample["December 20_prefix"] == 995 and sample["December 20_review_suffix"] == 136
    assert sample["April 20_prefix"] == 595 and sample["April 20_review_suffix"] == 7
    assert sample.get("aug26_incomplete_rows") == 370
    assert sample.get("aug26_zero_volt_rows") == 557
    return dict(**observed, flight_sheets_with_review_suffix=review_sheets, critical_sheet_splits=sample)

def check_agv():
    failures = []
    raw = None
    for url in AGV_URLS:
        try:
            attempt = get(url)
            if len(attempt) == 2265463 and hashlib.md5(attempt).hexdigest() == MD5_AGV:
                raw = attempt
                break
            failures.append("size or MD5 mismatch at " + url.split("?")[0])
        except Exception as exc:
            failures.append(str(exc))
    assert raw is not None, "AGV original could not be verified: " + "; ".join(failures)
    reader = csv.DictReader(io.StringIO(raw.decode("ascii")))
    assert tuple(reader.fieldnames or ()) == ("counter","date","cycletime","totaldischarge","mintemperature","maxtemperature","battery")
    bypack = collections.defaultdict(list)
    zero_row_verified = False
    rows = 0
    for rows, row in enumerate(reader, 1):
        pack, date, seconds = row["battery"], row["date"], int(row["cycletime"])
        assert seconds >= 0
        bypack[pack].append((date, seconds))
        if rows + 1 == 32797:
            zero_row_verified = pack == "FB-0" and date == "2021-05-11" and seconds == 0 and int(row["counter"]) == 18905
    assert rows == 57880 and len(bypack) == 10 and zero_row_verified
    thresholds = {}
    for min_n in (10, 20, 30, 50, 100):
        measures = {}
        for pack, events in sorted(bypack.items()):
            month = collections.defaultdict(list)
            for date, seconds in events:
                if date[:4] in ("2020", "2021"):
                    month[date[:7]].append(seconds)
            comps = []
            for m in range(1, 13):
                a = month.get(f"2020-{m:02d}", [])
                b = month.get(f"2021-{m:02d}", [])
                if min(len(a), len(b)) >= min_n and statistics.median(a) > 0:
                    n = min(len(a), len(b))
                    comps.append((n, 100 * (statistics.median(b) / statistics.median(a) - 1)))
            measures[pack] = round(sum(n * v for n, v in comps) / sum(n for n, _ in comps), 6) if comps else None
        thresholds[str(min_n)] = {
            "pct_by_battery": measures,
            "negative_packs": sum(v is not None and v < 0 for v in measures.values()),
            "positive_packs": sum(v is not None and v > 0 for v in measures.values()),
            "insufficient_packs": sum(v is None for v in measures.values()),
        }
    assert thresholds["20"]["negative_packs"] == 9 and thresholds["20"]["positive_packs"] == 1, thresholds["20"]
    assert thresholds["20"]["pct_by_battery"]["FB-5"] > 0
    return {"bytes": len(raw), "md5": MD5_AGV, "sha256": hashlib.sha256(raw).hexdigest(),
            "rows": rows, "packs": len(bypack), "known_zero_time_row_preserved": zero_row_verified,
            "calendar_month_threshold_sensitivity": thresholds}


def main():
    tsuru = check_tsuru()
    agv = check_agv()
    result = {
        "status": "BOTH_ORIGINAL_BYTES_REPLAYED_AND_PINNED",
        "executed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tsuru": tsuru, "agv": agv,
        "science_limit": "No satellite physical fault, AGV state-of-health, capacity fade, or causal aging claim",
    }
    Path("TSURU_AGV_REAL_SOURCE_CI_RECEIPT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "TSURU_CRC_members": tsuru["zip_members_full_crc_pass"],
                      "TSURU_source_rows": tsuru["rows_excluding_headers"],
                      "AGV_rows": agv["rows"], "matched_negative": agv["calendar_month_threshold_sensitivity"]["20"]["negative_packs"],
                      "matched_positive": agv["calendar_month_threshold_sensitivity"]["20"]["positive_packs"]}))


if __name__ == "__main__":
    main()
