#!/usr/bin/env python3
"""Read-only, bandwidth-capped preflight for RWTH's 48-cell public dataset.

No ZIP is downloaded, decompressed, executed or redistributed. The purpose is
to establish real source reachability, length and HTTP Range support before a
bounded, explicitly authorized follow-up analysis. CC BY 4.0, attribution:
RWTH Aachen ISEA, DOI 10.18154/RWTH-2021-04545 (2021).
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse

SOURCE_URL = "https://publications.rwth-aachen.de/record/818642/files/Rawdata.zip"
DOI = "10.18154/RWTH-2021-04545"
MAX_RANGED_BYTES = 256
MAX_ARCHIVE_BYTES = 160_000_000  # upper bound for optional later source download
TRUSTED_HOSTS = {"publications.rwth-aachen.de"}


def safe_size(content_length: str | None, content_range: str | None) -> int | None:
    """Prefer Content-Range total for GET 206; allow strict digit lengths."""
    if content_range:
        match = re.fullmatch(r"bytes\s+\d+-\d+/(\d+)", content_range.strip(), re.I)
        if not match:
            raise ValueError("SOURCE_REVIEW_REQUIRED: malformed Content-Range")
        total = int(match.group(1))
    elif content_length and re.fullmatch(r"[0-9]+", content_length):
        total = int(content_length)
    else:
        return None
    if total <= 0:
        raise ValueError("SOURCE_REVIEW_REQUIRED: invalid archive length")
    return total


def classify_probe(*, status: int, content_type: str, content_length: str | None,
                   content_range: str | None, head: bytes, final_url: str) -> dict:
    """Proof is metadata-only, not proof of full ZIP integrity or cell contents."""
    dest = urlparse(final_url)
    if dest.scheme != "https" or dest.hostname not in TRUSTED_HOSTS:
        raise ValueError("SOURCE_REVIEW_REQUIRED: unexpected redirect host")
    if status not in (200, 206):
        raise ValueError("SOURCE_REVIEW_REQUIRED: source unavailable")
    if len(head) > MAX_RANGED_BYTES or not head.startswith(b"PK\x03\x04"):
        raise ValueError("SOURCE_REVIEW_REQUIRED: not recognizable ZIP header")
    ct = (content_type or "").split(";")[0].lower().strip()
    if ct not in ("application/zip", "application/octet-stream", "application/x-zip-compressed"):
        raise ValueError("SOURCE_REVIEW_REQUIRED: unrecognized content type")
    if status == 200:
        # A server that ignored Range cannot prove bounded retrieval.
        return {"decision": "MANUAL_SOURCE_BUDGET_REVIEW", "http_status": status,
                "size_bytes": safe_size(content_length, None), "range_verified": False}
    total = safe_size(content_length, content_range)
    if total is None:
        raise ValueError("SOURCE_REVIEW_REQUIRED: archive length unavailable")
    if not content_range or not re.fullmatch(r"bytes\s+0-\d+/\d+", content_range.strip(), re.I):
        raise ValueError("SOURCE_REVIEW_REQUIRED: inconsistent range reply")
    return {"decision": "BOUNDED_ARCHIVE_FEASIBLE" if total <= MAX_ARCHIVE_BYTES
            else "LARGE_ARCHIVE_REQUIRE_PARTIAL_SOURCE_ACCESS",
            "http_status": status, "size_bytes": total, "range_verified": True}


def probe_source(url: str = SOURCE_URL) -> dict:
    if url != SOURCE_URL:
        raise ValueError("SOURCE_REVIEW_REQUIRED: source is not the pinned publisher URL")
    req = Request(url, headers={
        "Range": f"bytes=0-{MAX_RANGED_BYTES-1}",
        "Accept-Encoding": "identity",
        "User-Agent": "CANO-battery-research-source-preflight/1.0",
    })
    # Read at most 256 bytes; the body cannot exhaust free runner disk or RAM.
    with urlopen(req, timeout=24) as res:
        sample = res.read(MAX_RANGED_BYTES)
        meta = {"http_status": res.status,
                "type": res.headers.get("Content-Type", "")[:100],
                "length": res.headers.get("Content-Length"),
                "range": res.headers.get("Content-Range"),
                "host": urlparse(res.url).hostname,
                "prefix_hex_first_8": sample[:8].hex(),
                "sample_bytes": len(sample)}
        print("PUBLISHER_HTTP_DIAGNOSTIC:", json.dumps(meta, sort_keys=True), flush=True)
        info = classify_probe(
            status=res.status,
            content_type=res.headers.get("Content-Type", ""),
            content_length=res.headers.get("Content-Length"),
            content_range=res.headers.get("Content-Range"),
            head=sample, final_url=res.url)
    return {"schema": "cano.battery.rwth48-preflight.v1", "source_url": SOURCE_URL,
            "publisher": "RWTH Aachen ISEA", "doi": DOI,
            "license": "CC BY 4.0 — attribution required",
            "expected_physical_cells_in_publication": 48,
            "max_optional_full_archive_bytes": MAX_ARCHIVE_BYTES,
            "retrieved_bytes_max": MAX_RANGED_BYTES,
            "source_integrity_full_zip": "NOT_CHECKED",
            "physical_measurement_validation": "NOT_RUN",
            **info}


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("usage: rwth48_source_preflight.py OUTPUT_JSON", file=sys.stderr)
        return 2
    try:
        report = probe_source()
        out = Path(argv[0])
        if out.exists() or not out.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: output exists or parent is missing")
        with out.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
        print("RWTH48_PREFLIGHT:", json.dumps(report, sort_keys=True))
        # 0 means metadata audit completed; never implies full science validation.
        return 0
    except (URLError, HTTPError, ValueError, OSError) as exc:
        print("SOURCE_REVIEW_REQUIRED:", str(exc)[:180], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
