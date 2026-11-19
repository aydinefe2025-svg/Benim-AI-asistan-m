#!/usr/bin/env python3
"""Fail-closed external field-data source audit; NO physical cell claim yet.

Source: "Energy Storage Power Station Lithium-Ion Battery Real-World Operation
Dataset", Zenodo record 18471156 (2026). 19.2MB original BatteryData.zip.
Publisher MD5 c28d865877bdacf1cdc16130f4b73cfe. License needs separate review.
No personal/customer uploads, no direct ZIP extraction, no code execution.
"""
from __future__ import annotations
import collections
from hashlib import md5,sha256
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import zipfile

RECORD = "https://zenodo.org/records/18471156"
DOI = "10.5281/zenodo.18471156"
ORIGINAL_MD5 = "c28d865877bdacf1cdc16130f4b73cfe"
MAX_DOWNLOAD_BYTES = 28_000_000
MAX_MEMBERS = 5000
MAX_TOTAL_UNCOMPRESSED = 950_000_000
MAX_MEMBER_UNCOMPRESSED = 250_000_000


def inspect_zip_bytes(raw: bytes) -> dict:
    """Only return source metadata and content types; never source rows."""
    raise NotImplementedError("TDD RED: original source archive contract")


def audit_original(raw: bytes, *, expected_md5: str = ORIGINAL_MD5) -> dict:
    """Verify original publisher checksum before archive inspection."""
    raise NotImplementedError("TDD RED: immutable publisher digest contract")


def main() -> int:
    if len(sys.argv)!=3:
        print("usage: field_18471156_source.py publisher.zip source_report.json",file=sys.stderr)
        return 2
    try:
        archive=Path(sys.argv[1])
        report=Path(sys.argv[2])
        if not archive.is_file() or archive.is_symlink() or archive.stat().st_size>MAX_DOWNLOAD_BYTES:
            raise ValueError("SOURCE_REVIEW_REQUIRED: missing, unsafe or oversized source")
        result=audit_original(archive.read_bytes())
        if report.exists() or not report.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: report exists or parent missing")
        with report.open("x",encoding="utf-8") as dst:
            json.dump(result,dst,ensure_ascii=False,sort_keys=True,indent=2)
            dst.write("\n")
        print("PUBLISHER_SOURCE_ONLY:",json.dumps({
            "decision":result["decision"],"members":result["member_count"],
            "formats":result["format_counts"],
            "uncompressed_bytes":result["total_uncompressed_bytes"],
        },sort_keys=True))
        return 0
    except (OSError,ValueError,zipfile.BadZipFile,NotImplementedError) as exc:
        print("SOURCE_REVIEW_REQUIRED:",str(exc)[:170],file=sys.stderr)
        return 2

if __name__=="__main__":
    raise SystemExit(main())
