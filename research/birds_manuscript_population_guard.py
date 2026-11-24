#!/usr/bin/env python3
"""Fail-closed check: published BIRDS benchmark labels != 4-workbook samples.

The 2022 Applied Sciences anomaly-ML paper evaluates 8,439 three-satellite
BIRDS-3 observations from June 2019 through October 2020. The original XLSX
workbooks verified by the four-satellite replay contain mostly later sheets.
Here date bounds are evidenced by workbook SHEET NAMES, not by absolute UTC
per-row timestamps (column A is within-file relative seconds).

This does not recreate a publisher's curated labels or underlying benchmark.
"""
import datetime as dt
import json
from pathlib import Path

PAPER = {
    "doi": "10.3390/app12178634",
    "reported_n": 8439,
    "window_begin": "2019-06-01",
    "window_end": "2020-10-31",
    "reported_type1_fraction_pct": 8.59,
    "reported_type2_fraction_pct": 7.22,
    "reported_any_fraction_pct": 15.78,
    "publication": "Performance Evaluation of Machine Learning Methods for Anomaly Detection in CubeSat Solar Panels (2022)",
}
SOURCES = {
    "UGUISU": ("d230734c0955776bbe0abcda12c6f5d87eb940c1", 737659, 3270, 3260),
    "RAAVANA": ("f0bc233f8e7d5f5b9585c3fb8c794486132cb111", 485809, 2159, 2159),
    "NEPALISAT": ("8128db6a60f9058976c1147f3d6ade690dbfea17", 745668, 3040, 3040),
}

def sheet_date(title):
    for fmt in ("%d %b %Y", "%d %B %Y"):
        try:
            date = dt.datetime.strptime(title, fmt).date()
            # Reject lax parsing and inferred years.
            if date.strftime(fmt).lstrip("0").lower() != title.lstrip("0").lower():
                # Support whitespace and spelling differences only via alternate parser.
                continue
            return date
        except ValueError:
            continue
    raise ValueError("Unparseable original BIRDS worksheet date: " + repr(title))

def audit_population(receipt):
    if receipt.get("status") != "FOUR_SATELLITE_SOURCE_IDENTITIES_AND_OOXML_PROFILE_VERIFIED":
        raise ValueError("original pinned four-workbook source receipt missing")
    satellites = receipt["satellites"]
    result = {"source_rows": 0, "complete_14_field_rows": 0, "total_sheets": 0,
              "sheets_within_paper_window": 0, "sheets_outside_paper_window": 0,
              "source_rows_within_paper_window_by_sheet": 0,
              "source_rows_outside_paper_window_by_sheet": 0,
              "complete_rows_within_paper_window_by_sheet": 0,
              "complete_rows_outside_paper_window_by_sheet": 0,
              "sheet_date_span": [], "satellites": {}}
    start = dt.date.fromisoformat(PAPER["window_begin"])
    end = dt.date.fromisoformat(PAPER["window_end"])
    for name, (git_id, size, expected_raw, expected_complete) in SOURCES.items():
        src = satellites[name]
        if (src["git_blob_sha1"] != git_id or src["source_size"] != size or
            src["rows_after_first_total"] != expected_raw or
            src["numeric_14field_rows"] != expected_complete):
            raise ValueError(name + " original source pin or population changed")
        details = src["sheet_details"]
        if len(details) != src["sheet_count"] or len({s["sheet"] for s in details}) != len(details):
            raise ValueError(name + " duplicate or missing worksheets")
        if (sum(s["data_rows_after_first"] for s in details) != expected_raw or
            sum(s["numeric_14field_rows"] for s in details) != expected_complete):
            raise ValueError(name + " worksheet/source population mismatch")
        total_dates = []
        for sheet in details:
            sheet_name = sheet["sheet"]
            date = sheet_date(sheet_name)
            total_dates.append(date)
            raw_count = sheet["data_rows_after_first"]
            complete_count = sheet["numeric_14field_rows"]
            if not (isinstance(raw_count, int) and isinstance(complete_count, int) and
                    0 <= complete_count <= raw_count):
                raise ValueError(name + " invalid row counts")
            within = start <= date <= end
            label = "within" if within else "outside"
            result["sheets_" + label + "_paper_window"] += 1
            result["source_rows_" + label + "_paper_window_by_sheet"] += raw_count
            result["complete_rows_" + label + "_paper_window_by_sheet"] += complete_count
            result["sheet_date_span"].append({"satellite": name, "sheet": sheet_name,
                                              "sheet_date": date.isoformat(),
                                              "source_rows": raw_count,
                                              "complete_14_rows": complete_count,
                                              "inside_paper_window": within})
        result["satellites"][name] = {
            "sheets": len(details), "source_rows": expected_raw,
            "complete_14_rows": expected_complete,
            "first_worksheet_date": min(total_dates).isoformat(),
            "last_worksheet_date": max(total_dates).isoformat(),
        }
        result["source_rows"] += expected_raw
        result["complete_14_field_rows"] += expected_complete
        result["total_sheets"] += len(details)
    if (result["source_rows"] != result["source_rows_within_paper_window_by_sheet"]
            + result["source_rows_outside_paper_window_by_sheet"]):
        raise ValueError("population partition did not reconcile")
    paper_same = bool(result["sheets_outside_paper_window"] == 0 and
                      result["source_rows"] == PAPER["reported_n"])
    return {
        "status": "PUBLISHER_POPULATION_CONCORDANCE_AUDITED_WITH_SOURCE_SHEET_DATES",
        "publisher_paper": PAPER,
        "original_three_birds": result,
        "acceptance": {
            "paper_8439_same_population_as_original_workbooks": paper_same,
            "published_test_metrics_reproduced": False,
            "publisher_manually_curated_labels_present_in_original_workbooks": False,
            "original_source_identity_and_worksheet_counts_confirmed": True,
        },
        "limitations": [
            "Worksheet name gives measurement collection date; source A timestamp is relative seconds, not independent absolute UTC.",
            "Paper 8439 records and its manual labels are NOT the later pinned BIRDS original XLSX population.",
            "The manuscript class prevalence and machine learning F1 cannot be claimed reproduced on different sample dates or label definitions.",
            "Fault screening can be reproduced from original numeric telemetry; physical fault cause still requires independent engineering evidence.",
        ],
    }

def main():
    src = Path("BIRDS_FOUR_EPS_CI_RECEIPT.json")
    if not src.is_file():
        raise RuntimeError("real-source replay receipt missing, refusing synthetic success")
    out = audit_population(json.loads(src.read_text(encoding="utf8")))
    assert not out["acceptance"]["paper_8439_same_population_as_original_workbooks"]
    assert out["original_three_birds"]["source_rows_outside_paper_window_by_sheet"] > 0
    Path("BIRDS_2022_PAPER_POPULATION_CONCORDANCE_RECEIPT.json").write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf8")
    print("PUBLISHER_PAPER_SOURCE_POPULATION_AUDIT=" + json.dumps({
        "paper_reported_n": PAPER["reported_n"],
        "pinned_source_n": out["original_three_birds"]["source_rows"],
        "source_sheets_outside_manuscript_date_window": out["original_three_birds"]["sheets_outside_paper_window"],
        "source_rows_outside_manuscript_date_window": out["original_three_birds"]["source_rows_outside_paper_window_by_sheet"],
        "same_population": out["acceptance"]["paper_8439_same_population_as_original_workbooks"],
    }, sort_keys=True))

if __name__ == "__main__":
    main()