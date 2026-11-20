#!/usr/bin/env python3
"""Checksum-verified ORIGINAL small Figshare CSV; no waveform inference."""
from __future__ import annotations
from hashlib import md5, sha256
import csv
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from research.battery_curve_audit.multistage_25975315_preflight import (
    ARTICLE_ID, URL, MAX_META, audit_article, parse_metadata
)

CSV_FILE_ID = 47627029
CSV_EXPECTED_BYTES = 30658
MAX_ORIGINAL_CSV_BYTES = 50000
MAX_ROWS = 10000
MAX_COLUMNS = 100
SOURCE_FILE_URL = f"https://ndownloader.figshare.com/files/{CSV_FILE_ID}"


def locate_publisher_file(meta: dict) -> dict:
    """Require a unique pinned file entry and publisher-provided MD5."""
    receipt = audit_article(meta)
    if receipt["license_status"] != "CC_BY_4_0_PUBLISHER_METADATA":
        raise ValueError("SOURCE_REVIEW_REQUIRED: source license")
    matches = [f for f in meta["files"] if f["id"] == CSV_FILE_ID]
    if len(matches) != 1:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original file ID missing or duplicate")
    entry = matches[0]
    if entry["size"] != CSV_EXPECTED_BYTES:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original file size changed")
    if not entry["name"].lower().endswith(".csv"):
        raise ValueError("SOURCE_REVIEW_REQUIRED: source file not CSV")
    expected = entry.get("computed_md5") or entry.get("supplied_md5")
    if not isinstance(expected, str) or not re.fullmatch("[0-9a-fA-F]{32}", expected):
        raise ValueError("SOURCE_REVIEW_REQUIRED: no publisher MD5")
    return {"file_id": CSV_FILE_ID, "file_bytes": entry["size"],
            "publisher_md5": expected.lower(),
            "source_file_type": "csv",
            "publisher_meta_sha256": receipt.get("publisher_metadata_sha256")}


def inspect_original_csv(raw: bytes, publisher: dict) -> dict:
    """Enforce MD5 and CSV shape; never expose individual cell IDs or rows."""
    if not isinstance(raw, bytes) or len(raw) > MAX_ORIGINAL_CSV_BYTES:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original file byte limit")
    if len(raw) != publisher["file_bytes"]:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original byte count")
    orig_md5 = md5(raw).hexdigest()
    if orig_md5 != publisher["publisher_md5"]:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original publisher MD5 mismatch")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("SOURCE_REVIEW_REQUIRED: source not UTF-8 CSV") from None
    if "\x00" in content:
        raise ValueError("SOURCE_REVIEW_REQUIRED: binary byte in CSV")
    csv.field_size_limit(5000)
    reader = csv.DictReader(io.StringIO(content, newline=""))
    header = reader.fieldnames
    if not header or len(header) > MAX_COLUMNS:
        raise ValueError("SOURCE_REVIEW_REQUIRED: no valid header")
    normalized = [h.strip().lower() for h in header if isinstance(h, str)]
    if len(normalized) != len(header) or len(set(normalized)) != len(header):
        raise ValueError("SOURCE_REVIEW_REQUIRED: duplicate/bad CSV column")
    if any(len(h) < 1 or len(h) > 100 or not re.fullmatch(r"[a-zA-Z0-9_ ()/%.,\-\u00b0]+", h)
           for h in header):
        raise ValueError("SOURCE_REVIEW_REQUIRED: invalid CSV header")
    serial = header[normalized.index("serial")] if "serial" in normalized else None
    stage = header[normalized.index("stage")] if "stage" in normalized else None
    seen, seen_stage = set(), set()
    row_count, empty_serial = 0, 0
    for row in reader:
        row_count += 1
        if row_count > MAX_ROWS:
            raise ValueError("SOURCE_REVIEW_REQUIRED: excessive source rows")
        if None in row or len(row) != len(header):
            raise ValueError("SOURCE_REVIEW_REQUIRED: inconsistent source CSV row")
        if serial is not None:
            value = str(row[serial] or "").strip()
            if not value:
                empty_serial += 1
            else:
                seen.add(value)
                if stage is not None:
                    seen_stage.add((str(row[stage] or "").strip(), value))
    if row_count == 0:
        raise ValueError("SOURCE_REVIEW_REQUIRED: empty CSV")
    return {
        "schema": "cano.battery.figshare25975315.original-small-csv-metadata.v1",
        "source": "official_figshare_original_file",
        "article_id": ARTICLE_ID,
        "original_file_id": CSV_FILE_ID,
        "original_file_bytes": len(raw),
        "original_md5_matches_publisher": True,
        "original_file_md5": orig_md5,
        "original_file_sha256": sha256(raw).hexdigest(),
        "file_format": "csv",
        "column_count": len(header),
        "header_field_names": header,
        "record_rows": row_count,
        "has_serial_column": serial is not None,
        "has_stage_column": stage is not None,
        "rows_missing_serial": empty_serial if serial is not None else None,
        "distinct_serial_values": len(seen) if serial is not None else None,
        "distinct_stage_serial_pairs": len(seen_stage) if stage is not None and serial is not None else None,
        "contains_full_time_voltage_waveforms": False,
        "raw_cell_waveforms_downloaded": 0,
        "independently_authenticated_physical_cell_identities": 0,
        "cross_cell_confusion_rate_measured": False,
        "production_release_allowed": False,
        "decision": "SOURCE_CSV_MD5_AND_STRUCTURE_VERIFIED_NOT_PHYSICAL_VALIDATION",
    }


def _read_exact_source(url: str, limit: int) -> bytes:
    with urlopen(Request(url, headers={
        "User-Agent": "CANO-Research-Source-Checksum/1.0",
        "Accept": "application/json" if url == URL else "text/csv"
    }), timeout=35) as response:
        target = urlparse(response.geturl())
        if response.status != 200 or target.scheme != "https":
            raise ValueError("SOURCE_REVIEW_REQUIRED: HTTP/redirect")
        if url == URL and target.hostname != "api.figshare.com":
            raise ValueError("SOURCE_REVIEW_REQUIRED: publisher API host")
        if url != URL and not (
            target.hostname in ("figshare.com", "ndownloader.figshare.com")
            or (target.hostname or "").endswith(".figshare.com")
            or (target.hostname or "").endswith(".amazonaws.com")
        ):
            raise ValueError("SOURCE_REVIEW_REQUIRED: publisher file host")
        return response.read(limit + 1)


def fetch_original() -> dict:
    metadata_bytes = _read_exact_source(URL, MAX_META)
    meta = parse_metadata(metadata_bytes)
    publisher = locate_publisher_file(meta)
    original = _read_exact_source(SOURCE_FILE_URL, MAX_ORIGINAL_CSV_BYTES)
    out = inspect_original_csv(original, publisher)
    out["publisher_api_metadata_sha256"] = sha256(metadata_bytes).hexdigest()
    out["source_doi"] = meta["doi"]
    out["source_license"] = "CC_BY_4_0_PUBLISHER_METADATA"
    return out


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m research.battery_curve_audit.figshare25975315_small_csv output.json", file=sys.stderr)
        return 2
    try:
        dst = Path(sys.argv[1])
        if dst.exists() or not dst.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: destination invalid")
        out = fetch_original()
        with dst.open("x", encoding="utf-8") as fh:
            json.dump(out, fh, sort_keys=True, indent=2)
            fh.write("\n")
        print("PUBLISHER_SMALL_CSV", json.dumps({
            "sha256": out["original_file_sha256"],
            "rows": out["record_rows"],
            "columns": out["header_field_names"],
            "distinct_serial_values": out["distinct_serial_values"],
            "distinct_stage_serial_pairs": out["distinct_stage_serial_pairs"],
            "decision": out["decision"]
        }, sort_keys=True))
        return 0
    except (ValueError, OSError, csv.Error) as err:
        print("SOURCE_REVIEW_REQUIRED:", str(err)[:170], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
