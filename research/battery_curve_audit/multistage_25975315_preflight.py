#!/usr/bin/env python3
"""Publisher-only metadata audit for Stroebl et al. Figshare article 25975315.

NO publisher time-voltage samples are downloaded or analyzed by this module.
The peer-reviewed paper reports 279 cells; 279 is NOT a verified raw-data count.
"""
from __future__ import annotations
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ARTICLE_ID = 25975315
DOI = "10.6084/m9.figshare.25975315"
URL = "https://api.figshare.com/v2/articles/25975315"
PAPER_DOI = "10.1038/s41597-024-03859-z"
MAX_META = 2_000_000
MAX_FILES = 5000
MAX_TOTAL = 100_000_000_000
MAX_SINGLE = 30_000_000_000
SMALL_FILE = 25_000_000


def parse_metadata(data: bytes) -> dict:
    if not isinstance(data, bytes) or not 2 <= len(data) <= MAX_META:
        raise ValueError("SOURCE_REVIEW_REQUIRED: metadata byte budget")
    try:
        obj = json.loads(data)
    except (ValueError, UnicodeError):
        raise ValueError("SOURCE_REVIEW_REQUIRED: not publisher JSON") from None
    if not isinstance(obj, dict):
        raise ValueError("SOURCE_REVIEW_REQUIRED: metadata object required")
    return obj


def license_ok(lic: object) -> bool:
    if not isinstance(lic, dict):
        return False
    name = str(lic.get("name") or "").strip().lower().replace("-", " ")
    url = urlparse(str(lic.get("url") or ""))
    return (name in ("cc by 4.0", "creative commons attribution 4.0 international",
                     "attribution 4.0 international", "attribution 4.0")
            and url.hostname == "creativecommons.org"
            and url.path.rstrip("/").lower() == "/licenses/by/4.0"
            and url.scheme in ("https", "http"))


def audit_article(obj: dict) -> dict:
    if not isinstance(obj, dict) or obj.get("id") != ARTICLE_ID:
        raise ValueError("SOURCE_REVIEW_REQUIRED: article ID")
    doi = str(obj.get("doi") or "").lower().strip()
    if not re.fullmatch(r"10\.6084/m9\.figshare\.25975315(?:\.v[0-9]+)?", doi):
        raise ValueError("SOURCE_REVIEW_REQUIRED: DOI")
    files = obj.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_FILES:
        raise ValueError("SOURCE_REVIEW_REQUIRED: empty/oversized file list")
    seen_ids, seen_names, formats, small = set(), set(), Counter(), []
    total, missing_md5 = 0, 0
    for item in files:
        if not isinstance(item, dict):
            raise ValueError("SOURCE_REVIEW_REQUIRED: file item")
        fid, name, size = item.get("id"), item.get("name"), item.get("size")
        if not isinstance(fid, int) or isinstance(fid, bool) or fid <= 0:
            raise ValueError("SOURCE_REVIEW_REQUIRED: file ID")
        if not isinstance(name, str) or not 1 <= len(name) <= 200:
            raise ValueError("SOURCE_REVIEW_REQUIRED: file name")
        if ("/" in name or "\\" in name or ".." in name
                or "\x00" in name or name.startswith(".")):
            raise ValueError("SOURCE_REVIEW_REQUIRED: unsafe file name")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_SINGLE:
            raise ValueError("SOURCE_REVIEW_REQUIRED: file size")
        if fid in seen_ids or name.casefold() in seen_names:
            raise ValueError("SOURCE_REVIEW_REQUIRED: duplicate file")
        seen_ids.add(fid)
        seen_names.add(name.casefold())
        total += size
        if total > MAX_TOTAL:
            raise ValueError("SOURCE_REVIEW_REQUIRED: total size")
        ext = PurePosixPath(name).suffix.lower().lstrip(".") or "none"
        formats[ext] += 1
        digest = item.get("computed_md5") or item.get("supplied_md5")
        valid_md5 = isinstance(digest, str) and bool(
            re.fullmatch(r"[a-fA-F0-9]{32}", digest))
        if not valid_md5:
            missing_md5 += 1
        if 0 < size <= SMALL_FILE and ext in ("csv", "txt", "json", "md"):
            small.append({"file_id": fid, "bytes": size, "format": ext,
                          "publisher_md5_present": valid_md5})
    small.sort(key=lambda x: (x["bytes"], x["file_id"]))
    lic = "CC_BY_4_0_PUBLISHER_METADATA" if license_ok(obj.get("license")) else "NOT_VERIFIED"
    return {
        "schema": "cano.battery.figshare25975315.publisher-metadata.v1",
        "article_id": ARTICLE_ID, "doi": doi, "paper_doi": PAPER_DOI,
        "license_status": lic,
        "file_count_metadata": len(files),
        "total_bytes_metadata": total,
        "format_counts_metadata": dict(sorted(formats.items())),
        "missing_publisher_md5_count": missing_md5,
        "small_text_candidates_count": len(small),
        "small_text_candidates_first_20": small[:20],
        "original_files_downloaded": 0,
        "verified_independent_physical_cells": 0,
        "paper_reported_cells_not_checked": 279,
        "paper_reported_conditions_not_checked": 93,
        "raw_time_axis_verified": False,
        "time_voltage_pairs_measured": 0,
        "field_false_match_rate_calculated": False,
        "production_release_allowed": False,
        "decision": "METADATA_ONLY_NOT_PHYSICAL_VALIDATION"
        if license_ok(obj.get("license")) else "SOURCE_LICENSE_REVIEW_REQUIRED",
    }


def fetch() -> dict:
    req = Request(URL, headers={"Accept": "application/json",
                                "User-Agent": "CANO-battery-source-preflight/1.0"})
    with urlopen(req, timeout=25) as response:
        actual = urlparse(response.geturl())
        if response.status != 200 or actual.scheme != "https" or actual.hostname != "api.figshare.com":
            raise ValueError("SOURCE_REVIEW_REQUIRED: API status or redirect")
        raw = response.read(MAX_META + 1)
    report = audit_article(parse_metadata(raw))
    report["publisher_metadata_sha256"] = sha256(raw).hexdigest()
    return report


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: multistage_25975315_preflight.py output.json", file=sys.stderr)
        return 2
    try:
        dest = Path(sys.argv[1])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: output exists/invalid parent")
        report = fetch()
        with dest.open("x", encoding="utf-8") as out:
            json.dump(report, out, indent=2, sort_keys=True)
            out.write("\n")
        print("PUBLISHER_METADATA_ONLY", json.dumps({
            "license": report["license_status"],
            "file_count": report["file_count_metadata"],
            "total_bytes": report["total_bytes_metadata"],
            "small_text_candidates": report["small_text_candidates_count"],
            "decision": report["decision"]
        }, sort_keys=True))
        return 0 if report["license_status"] == "CC_BY_4_0_PUBLISHER_METADATA" else 2
    except (ValueError, OSError) as exc:
        print("SOURCE_REVIEW_REQUIRED", str(exc)[:160], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
