#!/usr/bin/env python3
"""Bounded original-source audit of independently described 3-cell cycling data.

Zenodo 19380245, DOI 10.5281/zenodo.19380245 (ITB, 2026).
The paper/record describe 3 cells at DIFFERENT discharge C-rates. This audit
does not infer cross-cell error rates, time units or genuine trials from headers.
Only a redacted structure receipt leaves the runner; no raw samples are saved.
"""
from __future__ import annotations
from collections import Counter
from hashlib import md5, sha256
from io import BytesIO
import csv
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zipfile import ZipFile, BadZipFile

RECORD_ID = 19380245
DOI = "10.5281/zenodo.19380245"
API = f"https://zenodo.org/api/records/{RECORD_ID}"
NAME = "Cyclic_Testing_LiIon_1C_2C_2.75C.zip"
PUBLISHER_MD5 = "dbbe4612dafef790d5dd23d697456192"
MAX_METADATA = 1_000_000
MAX_ZIP = 145_000_000
MAX_FILES = 25000
MAX_UNPACKED_LISTED = 7_000_000_000
MAX_MEMBER_LISTED = 1_000_000_000
MAX_INSPECTED = 5_000_000
MAX_EXAMPLES = 9
TIME_FIELDS = {"time", "time(s)", "time_s", "timestamp", "datetime",
               "test_time", "test_time(s)", "test_time_s", "time_sec"}
VOLT_FIELDS = {"voltage", "voltage(v)", "voltage_v", "volt", "v", "v(v)"}
CURRENT_FIELDS = {"current", "current(a)", "current_a", "cur", "i(a)", "i"}


def _json_mapping(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_METADATA:
        raise ValueError("SOURCE_REVIEW_REQUIRED: API metadata bounds")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError("SOURCE_REVIEW_REQUIRED: API response not JSON") from None
    if not isinstance(value, dict):
        raise ValueError("SOURCE_REVIEW_REQUIRED: API response object")
    return value


def validate_publisher_metadata(meta: dict) -> dict:
    """Require exact source, license metadata and publisher's MD5+size."""
    if not isinstance(meta, dict) or meta.get("id") != RECORD_ID:
        raise ValueError("SOURCE_REVIEW_REQUIRED: Zenodo record ID")
    metadata = meta.get("metadata")
    if not isinstance(metadata, dict) or str(metadata.get("doi", "")).strip().lower() != DOI:
        raise ValueError("SOURCE_REVIEW_REQUIRED: DOI")
    licenses = []
    for item in metadata.get("rights", []):
        if isinstance(item, dict):
            licenses.extend(str(item.get(k) or "").lower() for k in ("id", "identifier", "title"))
    lic = metadata.get("license")
    if isinstance(lic, dict):
        licenses.extend(str(lic.get(k) or "").lower() for k in ("id", "title"))
    elif isinstance(lic, str):
        licenses.append(lic.lower())
    # Only recognized attribution license identifiers, never guessed from open access.
    licensed = any(re.search(r"(?:^|[^a-z])cc[-_ ]?by[-_ ]?4(?:[.]0)?(?:$|[^a-z0-9])", x)
                   or "creative commons attribution 4.0" in x for x in licenses)
    if not licensed:
        raise ValueError("SOURCE_REVIEW_REQUIRED: publisher CC BY 4.0 not established")
    files = meta.get("files")
    if not isinstance(files, list):
        raise ValueError("SOURCE_REVIEW_REQUIRED: publisher file list")
    selected = [f for f in files if isinstance(f, dict) and f.get("key") == NAME]
    if len(selected) != 1:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original filename missing/duplicate")
    item = selected[0]
    size = item.get("size")
    if type(size) is not int or not 0 < size <= MAX_ZIP:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original archive byte budget")
    checksum = str(item.get("checksum") or "").lower()
    if checksum not in ("md5:" + PUBLISHER_MD5, PUBLISHER_MD5):
        raise ValueError("SOURCE_REVIEW_REQUIRED: original publisher checksum")
    return {"original_size": size, "publisher_md5": PUBLISHER_MD5,
            "license": "CC_BY_4_0_ZENODO_RECORD", "doi": DOI}


def inspect_archive(raw: bytes, original: dict) -> dict:
    if not isinstance(raw, bytes) or len(raw) != original["original_size"] or len(raw) > MAX_ZIP:
        raise ValueError("SOURCE_REVIEW_REQUIRED: archive byte size")
    if md5(raw).hexdigest() != original["publisher_md5"]:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original MD5 mismatch")
    if not raw.startswith((b"PK\\x03\\x04", b"PK\\x05\\x06")):
        raise ValueError("SOURCE_REVIEW_REQUIRED: not ZIP data")
    try:
        with ZipFile(BytesIO(raw)) as archive:
            entries = [f for f in archive.infolist() if not f.is_dir()]
            if not 1 <= len(entries) <= MAX_FILES:
                raise ValueError("SOURCE_REVIEW_REQUIRED: member count")
            names, total, extensions, top_dirs, header_shapes = set(), 0, Counter(), Counter(), Counter()
            sampled, inspected = [], 0
            for entry in entries:
                name = entry.filename.replace("\\\\", "/")
                path = PurePosixPath(name)
                if (not name or name.startswith("/") or ".." in path.parts or
                    ":" in name or "\\x00" in name):
                    raise ValueError("SOURCE_REVIEW_REQUIRED: unsafe member path")
                if name.casefold() in names:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: duplicate ZIP member")
                names.add(name.casefold())
                if stat.S_IFMT(entry.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP symlink")
                if entry.flag_bits & 1 or entry.file_size > MAX_MEMBER_LISTED or entry.file_size < 0:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: encrypted/oversized ZIP member")
                total += entry.file_size
                if total > MAX_UNPACKED_LISTED:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP expansion budget")
                extensions[path.suffix.lower() or "none"] += 1
                if len(path.parts) > 1:
                    top_dirs[path.parts[0][:64]] += 1
                if (path.suffix.lower() != ".csv" or len(sampled) >= MAX_EXAMPLES or
                    entry.file_size > MAX_INSPECTED):
                    continue
                # Read entire bounded candidate so ZIP library verifies this member's CRC.
                with archive.open(entry) as inp:
                    source = inp.read(MAX_INSPECTED + 1)
                if len(source) != entry.file_size:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: partial member")
                inspected += 1
                try:
                    lines = source.decode("utf-8-sig").splitlines()
                    header = next(csv.reader(lines[:1]))
                except (UnicodeError, csv.Error, StopIteration):
                    raise ValueError("SOURCE_REVIEW_REQUIRED: bad original CSV header") from None
                normalized = [s.strip().lower().replace(" ", "") for s in header]
                if not header or len(header) > 100 or len(set(normalized)) != len(header):
                    raise ValueError("SOURCE_REVIEW_REQUIRED: malformed CSV schema")
                has_t = any(x in TIME_FIELDS for x in normalized)
                has_v = any(x in VOLT_FIELDS for x in normalized)
                has_i = any(x in CURRENT_FIELDS for x in normalized)
                header_shapes[f"t{int(has_t)}v{int(has_v)}i{int(has_i)}"] += 1
                sampled.append({"file_sha256": sha256(source).hexdigest(),
                                "bytes": len(source), "columns": len(header),
                                "time_header": has_t, "voltage_header": has_v,
                                "current_header": has_i,
                                "header_names": [re.sub(r"[^A-Za-z0-9_./()%-]", "", h)[:50]
                                                 for h in header[:25]],
                                "filename_is_cell_identity": False})
    except (BadZipFile, OSError, RuntimeError, EOFError):
        raise ValueError("SOURCE_REVIEW_REQUIRED: corrupted ZIP member") from None
    return {"schema": "cano.battery.zenodo19380245.source-survey.v1",
            "doi": DOI, "publisher_license_verified": True,
            "publisher_original_md5_verified": True,
            "original_bytes": len(raw), "original_sha256": sha256(raw).hexdigest(),
            "zip_file_count": len(entries), "zip_listed_unpacked_bytes": total,
            "extension_counts": dict(sorted(extensions.items())),
            "top_folder_counts": dict(sorted(top_dirs.items())),
            "csv_examples_crc_verified": inspected,
            "csv_example_column_checks": dict(sorted(header_shapes.items())),
            "csv_examples": sampled,
            "time_axis_per_cell_verified": False,
            "physical_cell_ids_independently_verified": 0,
            "whole_cell_holdout_calculated": False,
            "empirical_false_match_rate_calculated": False,
            "original_samples_archived": False,
            "customer_release_allowed": False,
            "decision": "ORIGINAL_SOURCE_STRUCTURE_ONLY_NO_CROSS_CELL_METRIC"}


def _download(url: str, limit: int) -> bytes:
    if urlparse(url).scheme != "https":
        raise ValueError("SOURCE_REVIEW_REQUIRED: non-HTTPS URL")
    with urlopen(Request(url, headers={"User-Agent": "CANO-Research-Zenodo-19380245/1.0"}),
                 timeout=180) as response:
        dest = urlparse(response.geturl())
        if response.status != 200 or dest.scheme != "https" or dest.hostname != "zenodo.org":
            raise ValueError("SOURCE_REVIEW_REQUIRED: source redirected away from Zenodo")
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("SOURCE_REVIEW_REQUIRED: network size limit")
    return raw


def run() -> dict:
    meta_raw = _download(API, MAX_METADATA)
    original = validate_publisher_metadata(_json_mapping(meta_raw))
    archive_url = "https://zenodo.org/records/19380245/files/" + NAME + "?download=1"
    raw = _download(archive_url, MAX_ZIP)
    result = inspect_archive(raw, original)
    result["api_sha256"] = sha256(meta_raw).hexdigest()
    return result


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: zenodo19380245_three_cell_source.py receipt.json", file=sys.stderr)
        return 2
    try:
        dest = Path(sys.argv[1])
        if dest.exists() or not dest.parent.is_dir():
            raise ValueError("SOURCE_REVIEW_REQUIRED: output path")
        result = run()
        with dest.open("x", encoding="utf-8") as fh:
            json.dump(result, fh, sort_keys=True, indent=2)
            fh.write("\\n")
        print(json.dumps({k: result[k] for k in
                          ("decision", "original_bytes", "zip_file_count",
                           "extension_counts", "csv_example_column_checks",
                           "top_folder_counts")}, sort_keys=True))
        return 0
    except (ValueError, OSError) as exc:
        print("SOURCE_REVIEW_REQUIRED: " + str(exc)[:200], file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
