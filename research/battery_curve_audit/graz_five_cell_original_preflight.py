"""Source-authenticated structural preflight only for Graz's FIVE-cell 2026 record.

DOI 10.5281/zenodo.22079387 (force prediction; NOT the four-cell swelling
dataset DOI 10.5281/zenodo.18315429). No impact or absolute calibration claims.
No source ZIP or raw signal measurements are published in this repository.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import io
import json
import pathlib
import posixpath
import re
import stat
import urllib.parse
import urllib.request
import zipfile

RECORD_ID = "22079387"
DOI = "10.5281/zenodo." + RECORD_ID
API = "https://zenodo.org/api/records/" + RECORD_ID
ARCHIVE_NAME = "Experimental data for battery compression force prediction under mechanical constraints.zip"
PUBLISHER_MD5 = "b9ed863766e30afbd0e309951c855d08"
MAX_ZIP_BYTES = 40_000_000
MAX_UNCOMPRESSED_BYTES = 1_000_000_000
GOAL_KEY = "graz-20261123-five-original-static-preload-archive-zip-structure"
PUBLISHER_CELLS = {"01":0, "02":1.5, "03":3, "04":5, "05":15}


def validate_manifest(record: dict) -> dict:
    if str(record.get("id")) != RECORD_ID or record.get("doi") != DOI:
        raise ValueError("wrong record identity: do NOT swap the four-cell Graz dataset")
    files = record.get("files")
    if not isinstance(files, list):
        raise ValueError("missing publisher file list")
    match = [f for f in files if f.get("key") == ARCHIVE_NAME]
    if len(match) != 1:
        raise ValueError("missing or duplicate expected five-cell publisher ZIP")
    f = match[0]
    if f.get("checksum", "").lower() != "md5:" + PUBLISHER_MD5:
        raise ValueError("publisher checksum does not match pinned five-cell source")
    size = f.get("size")
    if not isinstance(size, int) or not (1_000_000 < size <= MAX_ZIP_BYTES):
        raise ValueError("unexpected publisher ZIP size")
    rights = record.get("metadata", {}).get("rights")
    if rights is None:
        rights = []
    if not isinstance(rights, list):
        raise ValueError("unexpected publisher rights metadata")
    licenses = [x.get("id") for x in rights if isinstance(x, dict) and isinstance(x.get("id"), str)]
    link = f.get("links", {}).get("content") or API + "/files/" + urllib.parse.quote(ARCHIVE_NAME, safe="") + "/content"
    u = urllib.parse.urlsplit(link)
    if u.scheme != "https" or u.netloc != "zenodo.org" or not u.path.startswith("/api/records/" + RECORD_ID + "/files/"):
        raise ValueError("file link is not the fixed Zenodo publisher record")
    return {"file": ARCHIVE_NAME, "size": size, "md5": PUBLISHER_MD5,
            "license_ids_from_publisher_record": licenses, "download_url": link}


def get_bytes(url: str, cap: int) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "CANO-graz-source-audit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        chunks, total = [], 0
        while True:
            chunk = response.read(min(1 << 20, cap - total + 1))
            if not chunk:
                break
            total += len(chunk)
            if total > cap:
                raise ValueError("source exceeds byte cap")
            chunks.append(chunk)
    return b"".join(chunks)


def audit_archive(blob: bytes) -> dict:
    if not blob or len(blob) > MAX_ZIP_BYTES:
        raise ValueError("archive byte size invalid")
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValueError("not a valid ZIP archive")
    members = []
    sum_uncompressed = 0
    seen = set()
    counts = collections.Counter()
    with zipfile.ZipFile(io.BytesIO(blob), "r") as z:
        infos = z.infolist()
        if not infos or len(infos) > 2000:
            raise ValueError("archive member count outside bounded limits")
        for i in infos:
            name = i.filename
            normalized = posixpath.normpath(name)
            if (not name or "\\" in name or name.startswith("/") or ":" in name
                    or normalized in (".", "..") or normalized.startswith("../")
                    or name.startswith("./") or "\x00" in name):
                raise ValueError("unsafe archive member path")
            if name in seen:
                raise ValueError("duplicate archive path")
            seen.add(name)
            if stat.S_IFMT(i.external_attr >> 16) == stat.S_IFLNK:
                raise ValueError("archive symlink not allowed")
            sum_uncompressed += i.file_size
            if sum_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise ValueError("archive uncompressed size cap exceeded")
            if i.is_dir():
                continue
            suffix = pathlib.PurePosixPath(name).suffix.lower()
            counts[suffix or "(none)"] += 1
            record = {"path":name, "uncompressed_bytes":i.file_size,
                      "compressed_bytes":i.compress_size, "crc32_hex":format(i.CRC, "08x")}
            # Only small header/structure excerpts, never raw full measurements.
            if suffix in (".csv", ".txt", ".log", ".dat", ".tsv", ".asc") and len(members) < 120:
                with z.open(i) as f:
                    sample = f.read(1500)
                # Expose sanitized first two nonempty lines to identify schema.
                lines = sample.decode("utf-8", "replace").replace("\x00", "").splitlines()
                record["header_preview"] = [re.sub(r"[^\x20-\x7e]", "?", x)[:180]
                                            for x in lines if x.strip()][:2]
            members.append(record)
        error = z.testzip()
        if error is not None:
            raise ValueError("ZIP CRC failed in " + error)
    if not members:
        raise ValueError("no real data files")
    return {"zip_crc_all_members_pass": True, "file_count":len(members),
            "total_uncompressed_bytes":sum_uncompressed,
            "file_extension_counts":dict(sorted(counts.items())),
            "file_members":members}


def audit_original() -> dict:
    meta_raw = get_bytes(API, 2_000_000)
    manifest = validate_manifest(json.loads(meta_raw))
    blob = get_bytes(manifest["download_url"], MAX_ZIP_BYTES)
    if len(blob) != manifest["size"]:
        raise ValueError("downloaded bytes not equal original publisher byte size")
    archive_md5 = hashlib.md5(blob).hexdigest()
    if archive_md5 != PUBLISHER_MD5:
        raise ValueError("downloaded original source MD5 mismatch")
    structure = audit_archive(blob)
    return {"goal_key":GOAL_KEY, "publisher_record_doi":DOI,
            "publisher_record_id":RECORD_ID, "distinct_from_graz_four_cell_doi":"10.5281/zenodo.18315429",
            "publisher_metadata_sha256":hashlib.sha256(meta_raw).hexdigest(),
            "publisher_source_name":ARCHIVE_NAME,
            "source_bytes":len(blob), "publisher_md5":PUBLISHER_MD5,
            "recomputed_source_md5":archive_md5, "recomputed_source_sha256":hashlib.sha256(blob).hexdigest(),
            "license_ids_in_record":manifest["license_ids_from_publisher_record"],
            "publisher_declared_preloads_kN":PUBLISHER_CELLS,
            "source_byte_integrity_verified":True, "archive_structure":structure,
            "static_preload_not_dynamic_impact":True,
            "cell_id_time_series_join_verified":False,
            "source_column_units_verified":False,
            "source_capacity_recomputed":False,
            "individual_force_thickness_calibration_verified":False,
            "same_samples_as_four_cell_older_record_proven":False,
            "not_a_qualified_capacity_or_safety_model":True}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("output", type=pathlib.Path)
    args = p.parse_args()
    evidence = audit_original()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2,
                                      sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("GRAZ_FIVE_CELL_OFFICIAL_ZIP_MD5_SHA256_CRC_OK",
          evidence["source_bytes"], evidence["recomputed_source_sha256"], flush=True)
    print("FILE_EXTENSIONS", evidence["archive_structure"]["file_extension_counts"], flush=True)
    for m in evidence["archive_structure"]["file_members"][:40]:
        print("ORIGINAL_MEMBER", m["path"], m.get("header_preview", []), flush=True)
    print("NO_QUALIFIED_CELL_PAIRING_OR_IMPACT_CAPACITY_CLAIM", flush=True)


if __name__ == "__main__":
    main()
