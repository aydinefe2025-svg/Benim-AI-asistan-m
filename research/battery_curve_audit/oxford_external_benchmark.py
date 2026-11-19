#!/usr/bin/env python3
"""Independent real time-voltage benchmark; research-only, no field certification.

University of Oxford (Reniers, Mulder, Howey 2020), DOI
10.5287/bodleian:gJPdDzvP4, ODbL 1.0; data remain publisher-hosted.
The README identifies profile time [s], current [A], voltage [V].
Never treat a dataset index or state-of-charge as measurement time.
"""
from __future__ import annotations
import csv
from hashlib import sha256
import io
import json
import math
from pathlib import Path
import sys
from urllib.request import Request, urlopen

SOURCE = {
    "BMP_cell1": ("BMP_cell1_profileData.csv", "dcc08hf70v"),
    "BMP_cell2": ("BMP_cell2_profileData.csv", "dvx021f16r"),
}
OXFORD_ROOT = "https://ora.ox.ac.uk/objects/uuid:9aae61af-2949-49f1-8ad5-6aea448979e5/files/"
DOI = "10.5287/bodleian:gJPdDzvP4"
MAX_BYTES = 12_000_000
MAX_POINTS = 200_000


def parse_profile(raw: bytes) -> tuple[list[float], list[float]]:
    """Parse original Oxford profile-time/current/voltage; never guess units."""
    raise NotImplementedError("Parser acceptance tests are RED until implemented")


def audit_profiles(raw_by_id: dict[str, bytes]) -> dict:
    """Verify both real sources and run a controlled +1mV clone check."""
    raise NotImplementedError("Source acceptance tests are RED until implemented")


def fetch_originals() -> dict[str, bytes]:
    """Download only the two named Oxford original sources, bounded per file."""
    raws = {}
    for cell, (filename, file_id) in SOURCE.items():
        url = OXFORD_ROOT + file_id
        req = Request(url, headers={"User-Agent": "CANO-science-public-source-audit/1.0"})
        with urlopen(req, timeout=25) as res:
            if res.status != 200:
                raise ValueError("SOURCE_UNAVAILABLE: Oxford original not HTTP 200")
            data = res.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or len(data) < 1_000:
            raise ValueError("SOURCE_UNAVAILABLE: original file size outside source budget")
        raws[cell] = data
    return raws


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: oxford_external_benchmark.py output.json", file=sys.stderr)
        return 2
    try:
        result = audit_profiles(fetch_originals())
        out = Path(sys.argv[1])
        if out.exists() or not out.parent.exists():
            raise ValueError("REVIEW_REQUIRED: output exists or directory missing")
        with out.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, sort_keys=True, indent=2)
            handle.write("\n")
        print("SOURCE_VERIFIED: independent Oxford time-voltage; controlled clone screening OK; no field certification")
        return 0
    except (ValueError, OSError, UnicodeError, csv.Error, NotImplementedError) as exc:
        print(f"REVIEW_REQUIRED: {type(exc).__name__}: {str(exc)[:180]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
