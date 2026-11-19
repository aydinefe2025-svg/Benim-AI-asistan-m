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
    """Read-only archive CRC, member budget, and file-type inventory.

    No ZIP entry is written or executed. No filenames or original values are
    published in the receipt. Even a valid CRC does not verify sensor truth.
    """
    if not isinstance(raw, bytes) or not 4 <= len(raw) <= MAX_DOWNLOAD_BYTES:
        raise ValueError("SOURCE_REVIEW_REQUIRED: invalid or excessive archive length")
    if not raw.startswith((b"PK\x03\x04", b"PK\x05\x06")):
        raise ValueError("SOURCE_REVIEW_REQUIRED: source is not a ZIP header")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            members = [info for info in z.infolist() if not info.is_dir()]
            if not members or len(members)>MAX_MEMBERS:
                raise ValueError("SOURCE_REVIEW_REQUIRED: empty or excessive ZIP member count")
            total, seen, kinds = 0, set(), collections.Counter()
            safe_headers = collections.defaultdict(list)
            header_cols = collections.Counter()
            header_signatures = set()
            header_samples = []
            voltage_counts, temperature_counts, current_counts, time_counts = [], [], [], []
            for info in members:
                name = info.filename.replace("\\", "/")
                clean = PurePosixPath(name)
                if (not name or name.startswith("/") or
                    ".." in clean.parts or ":" in name or
                    "\x00" in name):
                    raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP path is unsafe")
                key=name.casefold()
                if key in seen:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: duplicate ZIP member")
                seen.add(key)
                if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP symbolic link")
                if info.file_size > MAX_MEMBER_UNCOMPRESSED or info.file_size < 0:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: excessive ZIP member size")
                total += info.file_size
                if total>MAX_TOTAL_UNCOMPRESSED:
                    raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP expansion budget exceeded")
                if info.file_size > 20_000_000 and (
                    info.compress_size < 1 or
                    info.file_size / info.compress_size > 500):
                    raise ValueError("SOURCE_REVIEW_REQUIRED: suspicious ZIP expansion ratio")
                ext=clean.suffix.casefold().lstrip(".") or "none"
                kinds[ext]+=1
                # Header tokens only, NOT voltage samples or private cell IDs.
                if ext in ("csv", "tsv", "txt"):
                    # Metadata-only scan of every published file header; no
                    # observation rows leave this in-memory research process.
                    with z.open(info) as src:
                        preview=src.read(1200)
                    first=preview.splitlines()[0] if preview.splitlines() else b""
                    line=first.decode("utf-8-sig","replace").replace(chr(9),",")
                    sep = ";" if line.count(";") > line.count(",") else ","
                    tokens=[col.strip()[:48] for col in line.split(sep)[:80]]
                    header_cols[str(len(tokens))] += 1
                    sanitized=[]
                    for word in tokens:
                        # Limit archive-provided text to simple short labels,
                        # never emit a numeric measurement as a header.
                        try:
                            float(word)
                            label="numeric-value-not-a-header"
                        except ValueError:
                            label="".join(c for c in word if
                                  c.isalnum() or c in "_- .()[]/%°")[:48]
                        sanitized.append(label)
                    header_signatures.add(sha256(json.dumps(
                        sanitized,ensure_ascii=False).encode("utf-8")).hexdigest())
                    normalized=[word.lower().replace(" ","") for word in sanitized]
                    voltage_counts.append(sum(
                        word.startswith(("vol_","voltage","cell_voltage"))
                        for word in normalized))
                    temperature_counts.append(sum(
                        word.startswith(("temp_","temperature")) for word in normalized))
                    current_counts.append(sum(
                        word in ("cur","current","current_a","i/a")
                        for word in normalized))
                    time_counts.append(sum(
                        word in ("time","time_s","time(s)","timestamp","datetime",
                                 "test_time(s)","test_time_s")
                        for word in normalized))
                    if len(header_samples)<3:
                        header_samples.append(sanitized[:24])
                    if len(safe_headers[ext]) < 3:
                        generic=[]
                        for word in tokens[:24]:
                            lower=word.lower()
                            labels=("time","volt","curr","temp","cell","soc","status",
                                    "date","cycle","power","capacity")
                            synonyms=(("时间","time"),("电压","volt"),("温度","temp"),
                                      ("电流","curr"))
                            kind=next((x for x in labels if x in lower),None)
                            if kind is None:
                                kind=next((value for needle,value in synonyms
                                           if needle in lower),"other")
                            generic.append(kind)
                        safe_headers[ext].append(generic)
            damaged = z.testzip()
            if damaged is not None:
                raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP member CRC mismatch")
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError) as exc:
        raise ValueError("SOURCE_REVIEW_REQUIRED: ZIP format, CRC or decompression failure") from None
    return {"member_count": len(members),
            "format_counts": dict(sorted(kinds.items())),
            "total_uncompressed_bytes": total,
            "zip_all_member_crc": "PASS",
            "safe_header_tokens_by_type": dict(safe_headers),
            "header_column_count_histogram": dict(sorted(header_cols.items())),
            "distinct_header_patterns": len(header_signatures),
            "header_samples": header_samples,
            "voltage_channel_count": voltage_counts[0] if voltage_counts and
                len(set(voltage_counts))==1 else None,
            "temperature_channel_count": temperature_counts[0] if temperature_counts and
                len(set(temperature_counts))==1 else None,
            "current_channel_count": current_counts[0] if current_counts and
                len(set(current_counts))==1 else None,
            "time_axis_status": (
                "MISSING" if time_counts and all(x==0 for x in time_counts)
                else "HEADER_PRESENT_NOT_UNITS_VALIDATED" if time_counts and all(x>0 for x in time_counts)
                else "INCONSISTENT_OR_UNREADABLE"
            ),
            "time_voltage_screening_allowed": False,
            "physical_cell_identity_confirmed": False}


def audit_original(raw: bytes, *, expected_md5: str = ORIGINAL_MD5) -> dict:
    """Require a publisher-pinned digest, then inspect ZIP with safe limits."""
    if not isinstance(raw,bytes) or not isinstance(expected_md5,str):
        raise ValueError("SOURCE_REVIEW_REQUIRED: missing publisher MD5")
    if md5(raw).hexdigest() != expected_md5:
        raise ValueError("SOURCE_REVIEW_REQUIRED: original publisher MD5 mismatch")
    meta=inspect_zip_bytes(raw)
    return {"schema":"cano.battery.real-field-source-integrity.v1",
            "doi": DOI, "source_url": RECORD,
            "source_file":"BatteryData.zip",
            "source_license": "UNKNOWN: metadata license not independently verified",
            "license_for_commercial_reuse": "NOT_VERIFIED",
            "publisher_md5_verified": True,
            "publisher_original_md5": expected_md5,
            "source_sha256": sha256(raw).hexdigest(),
            "compressed_bytes":len(raw),
            "decision":"SOURCE_INTEGRITY_ONLY_NOT_PHYSICAL_VALIDATION",
            "limitations":[
                "No source publication or independently confirmed physical cell identifiers.",
                "No field reference labels, reliability estimates, model calibration or commercial rights.",
                "ZIP checksum and CRC do not verify that measurements originate from calibrated sensors.",
                "Only source format inventory; no time-voltage duplicate comparisons performed.",
            ],**meta}


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
