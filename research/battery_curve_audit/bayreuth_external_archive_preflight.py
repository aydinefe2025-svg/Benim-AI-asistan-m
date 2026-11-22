"""Fail-closed source-integrity and schema preflight for one *independent* Zenodo cell.

Röder et al. (2025), DOI 10.5281/zenodo.15755725, CC BY 4.0.
This module downloads F0001.zip from the publisher in CI, checks the pinned
publisher MD5 and whole ZIP CRC, and records only archive-level metadata and
structural candidate names. No Stroebl raw files are read; no diagnosis is made.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import urllib.request
import zipfile
from pathlib import PurePosixPath, Path

DOI = "10.5281/zenodo.15755725"
SOURCE = "https://zenodo.org/records/15755725/files/F0001.zip?download=1"
EXPECTED_MD5 = "8181a89aee2e525ca52b60491ee3209b"
MIN_SOURCE_BYTES = 100_000
MAX_SOURCE_BYTES = 28_000_000
MAX_MEMBERS = 500


def validate_archive(raw: bytes) -> dict:
    """Never infer independence or measurement validity from a valid ZIP alone."""
    md5 = hashlib.md5(raw).hexdigest()
    if md5 != EXPECTED_MD5:
        raise ValueError(f"Source MD5 mismatch; expected {EXPECTED_MD5}, got {md5}")
    if not (MIN_SOURCE_BYTES <= len(raw) <= MAX_SOURCE_BYTES):
        raise ValueError("Original ZIP size outside safe 0.1–28 MB bound")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_MEMBERS:
            raise ValueError("Unexpected number of ZIP members")
        if (bad := archive.testzip()) is not None:
            raise ValueError("Corrupt archive ZIP CRC: " + bad)
        content = []
        types = {}
        for item in entries:
            if item.is_dir():
                continue
            path = PurePosixPath(item.filename.replace("\\", "/"))
            if ".." in path.parts or path.is_absolute():
                raise ValueError("ZIP path traversal or absolute path")
            suffix = path.suffix.lower() or "(none)"
            types[suffix] = types.get(suffix, 0) + 1
            content.append({"name": str(path), "size_bytes": item.file_size,
                            "packed_bytes": item.compress_size, "crc32": f"{item.CRC:08x}"})
        if not content:
            raise ValueError("Unexpected empty publisher ZIP")
        names = [x["name"].lower() for x in content]
        # The publisher describes M0001 and M0003 checkups. If the archive
        # layout differs, record it explicitly, not invent measurements.
        cues = {"beginning_checkup_M0001": any("m0001" in n and "checkup" in n for n in names),
                "final_checkup_M0003": any("m0003" in n and "checkup" in n for n in names),
                "aging_data_M0002": any("m0002" in n and "aging" in n for n in names)}
        return {"source_doi": DOI, "dataset_name": "Degradation path indicators for lithium-ion batteries",
                "study_group": "Röder et al., University of Bayreuth, 2025",
                "original_source_url": SOURCE, "source_cell_id": "F0001",
                "source_license": "CC BY 4.0", "source_publisher_md5": md5,
                "source_byte_count": len(raw), "zip_crc_all_pass": True,
                "zip_file_count": len(content), "file_type_counts": types,
                "publisher_description_cues_found": cues, "member_manifest": content,
                "cells_with_downloaded_original_zip": 1,
                "cells_reported_in_dataset_by_publishers": 48,
                "actual_DCIR_or_capacity_recalculated": False,
                "independent_lab_validation_of_original_Stroebl_4_cells": False,
                "physical_calibration_certificate_verified": False,
                "comparison_to_Stroebl_not_yet_performed": True}


def download_original() -> bytes:
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "CANO-source-integrity-preflight/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=75) as stream:
        chunks, size = [], 0
        while True:
            chunk = stream.read(1 << 20)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SOURCE_BYTES:
                raise ValueError("Source exceeded bounded download limit")
            chunks.append(chunk)
    return b"".join(chunks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = validate_archive(download_original())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("BAYREUTH_REAL_ORIGINAL_F0001_SOURCE_MD5_CRC_PASS",
          out["source_byte_count"], out["zip_file_count"], out["publisher_description_cues_found"])


if __name__ == "__main__":
    main()