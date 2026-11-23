"""Graz public original mechanical/electrical paired-source preflight (not impact).
Source Zenodo 10.5281/zenodo.22079387. No raw measurements published.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib, io, json, re, stat, zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen

RECORD=22079387
DOI="10.5281/zenodo.22079387"
FILENAME="Experimental data for battery compression force prediction under mechanical constraints.zip"
MD5="b9ed863766e30afbd0e309951c855d08"
MAX_ZIP=32_000_000
MAX_CONTENT=800_000_000

def download(url, size_limit):
    if not url.startswith("https://zenodo.org/"):
        raise ValueError("Not canonical Zenodo URL")
    req=Request(url, headers={"User-Agent":"CANO-Graz-open-research-source-audit/1"})
    with urlopen(req, timeout=65) as r:
        data=r.read(size_limit+1)
    if len(data)>size_limit:
        raise ValueError("Oversized HTTP response")
    return data

def check_metadata(meta):
    if str(meta.get("id")) != str(RECORD) or meta.get("doi")!=DOI:
        raise ValueError("Wrong DOI or record")
    matches=[f for f in meta.get("files",[]) if f.get("key")==FILENAME]
    if len(matches)!=1:
        raise ValueError("Unique publisher file missing")
    f=matches[0]
    if f.get("checksum")!="md5:"+MD5:
        raise ValueError("Publisher MD5 changed")
    size=f.get("size")
    if type(size)!=int or not 0<size<=MAX_ZIP:
        raise ValueError("Unsafe publisher file size")
    return size

def check_member(z):
    name=z.filename.replace("\\","/")
    if (not name or name.startswith("/") or re.match(r"^[a-zA-Z]:",name)
        or any(p in (".","..") for p in name.split("/"))
        or (z.external_attr>>16)&0o170000==stat.S_IFLNK
        or z.file_size<0 or z.file_size>MAX_CONTENT
        or z.file_size/max(1,z.compress_size)>1000):
        raise ValueError("Unsafe ZIP member")
    return name

def preview(raw):
    """Keep only short source header and format bytes; this is NOT a trace export."""
    if b"\0" in raw[:256]:
        text=raw.decode("utf-16",errors="replace")
        coding="utf-16"
    else:
        text=raw.decode("utf-8-sig",errors="replace")
        coding="utf-8-sig"
    lines=text.splitlines()[:80]
    clean=["".join(ch if (ch.isprintable() or ch=="\t") else "?" for ch in line)[:180]
           for line in lines]
    return {"text":True,"encoding_attempt":coding,"first_bytes_hex":raw[:64].hex(),
            "first_lines":clean}

def inventory(raw):
    names=[]; types=Counter(); seen=set(); examples=[]; sample_count=Counter(); total=0
    with zipfile.ZipFile(io.BytesIO(raw)) as zipf:
        infos=zipf.infolist()
        if len(infos)>5000:
            raise ValueError("Too many ZIP members")
        for item in infos:
            name=check_member(item)
            key=name.casefold()
            if key in seen:
                raise ValueError("Ambiguous ZIP member")
            seen.add(key)
            total+=item.file_size
            if total>MAX_CONTENT:
                raise ValueError("Archive uncompressed data exceeds limit")
            if not item.is_dir():
                names.append(name)
                types[PurePosixPath(name).suffix.lower() or "<none>"]+=1
        if zipf.testzip() is not None:
            raise ValueError("ZIP CRC mismatch")
        for item in sorted(infos,key=lambda x:x.filename.casefold()):
            if item.is_dir():continue
            ext=PurePosixPath(item.filename).suffix.lower() or "<none>"
            if sample_count[ext]>=3 or len(examples)>=40:continue
            with zipf.open(item) as f:
                data=f.read(16000)
            examples.append({"name":item.filename,"bytes":item.file_size,
                             "suffix":ext,"header":preview(data)})
            sample_count[ext]+=1
    return {"file_count":len(names),"uncompressed_bytes":total,
            "extensions":dict(sorted(types.items())),"names":sorted(names),
            "schema_examples":examples,"all_zip_crc_pass":True}

def audit():
    meta_url=f"https://zenodo.org/api/records/{RECORD}"
    meta=json.loads(download(meta_url,2_000_000))
    n=check_metadata(meta)
    raw=download(meta_url+"/files/"+quote(FILENAME)+"/content",MAX_ZIP)
    if len(raw)!=n or hashlib.md5(raw).hexdigest()!=MD5:
        raise ValueError("Real archive byte length or digest mismatch")
    return {"goal_key":"graz-20261123-original-paired-mech-electric-source-inventory-v1",
            "source":{"doi":DOI,"record_url":f"https://zenodo.org/records/{RECORD}",
                      "filename":FILENAME,"bytes":len(raw),"md5":MD5,
                      "sha256":hashlib.sha256(raw).hexdigest()},
            "inventory":inventory(raw),"source_verified":True,
            "same_cell_mechanical_electrical_join_verified":False,
            "mechanical_loading_is_dynamic_impact":False,
            "calibration_verified":False,
            "capacity_or_causal_effect_verified":False,
            "next_gate":"inspect original log/SP schemas and physically matched cell ID/time"}

def main():
    p=argparse.ArgumentParser();p.add_argument("--out",default="graz_original_schema_probe.json")
    args=p.parse_args()
    report=audit()
    Path(args.out).write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("GRAZ_ZENODO_ORIGINAL_SOURCE_VERIFIED",report["source"]["sha256"],
          report["inventory"]["file_count"])

if __name__=="__main__":main()
