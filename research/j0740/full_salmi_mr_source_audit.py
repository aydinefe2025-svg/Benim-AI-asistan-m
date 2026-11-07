"""Audit *full* Salmi 2024 headline M-R samples from the small source tarball.

Only the 40.6MB mr_samples_and_contours.tar.gz is needed, NOT the 12.9GB
model/data archive. Source MD5 is checked before any analysis. Exactly one
named tar member is streamed without writing archive paths to disk.
This is posterior-summary inference only, not photon likelihood or EOS Bayes.
"""
from __future__ import annotations
import argparse, hashlib, io, json, math, tarfile
from pathlib import Path
import numpy as np

SOURCE_ARCHIVE = "mr_samples_and_contours.tar.gz"
EXPECTED_MD5 = "ca8e70eeca81feb71321f1a88a24f2f9"
SOURCE_MEMBER = "mr_samples_and_contours/J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat"
EXPECTED_ROWS = 379669
SOURCE_DOI = "10.5281/zenodo.10519473"


def digest_file(path: Path, algo: str) -> str:
    h=hashlib.new(algo)
    with path.open('rb') as f:
        while block:=f.read(2**20):
            h.update(block)
    return h.hexdigest()


def summarize(m: np.ndarray, r: np.ndarray, expected_rows=EXPECTED_ROWS) -> dict:
    m=np.asarray(m,dtype=float); r=np.asarray(r,dtype=float)
    if (m.ndim!=1 or r.shape!=m.shape or len(m)!=expected_rows
            or not np.all(np.isfinite(m)) or not np.all(np.isfinite(r))
            or np.any((m<=0)|(m>=4)) or np.any((r<5)|(r>25))):
        raise ValueError("Unexpected full-source rows, shape, or physical range")
    quant=(.01,.05,.16,.5,.84,.95,.99)
    out={"rows":int(len(m)),"M_mean_msun":float(np.mean(m)),
         "M_quantiles_msun":{str(q):float(x) for q,x in zip(quant,np.quantile(m,quant))},
         "R_mean_km":float(np.mean(r)),
         "R_quantiles_km":{str(q):float(x) for q,x in zip(quant,np.quantile(r,quant))},
         "radius_tail_counts":{f"R>{threshold}km":int(np.count_nonzero(r>threshold)) for threshold in (14.,14.5,15.,15.5,16.)},
         "radius_tail_fractions":{f"R>{threshold}km":float(np.mean(r>threshold)) for threshold in (14.,14.5,15.,15.5,16.)},
         "radius_range_km":[float(np.min(r)),float(np.max(r))],
         "mass_range_msun":[float(np.min(m)),float(np.max(m))]}
    return out


def audit(archive: Path, *, expected_md5=EXPECTED_MD5, expected_rows=EXPECTED_ROWS) -> dict:
    if archive.name!=SOURCE_ARCHIVE:
        raise ValueError("Not the expected Salmi small headline tar archive filename")
    if not archive.is_file() or not (64 <= archive.stat().st_size<=60_000_000):
        raise ValueError("Missing/oversized archive; never use 12.9GB input")
    md5=digest_file(archive,"md5")
    if md5!=expected_md5:
        raise ValueError("Salmi 40.6MB source archive MD5 mismatch; STOP")
    sha=digest_file(archive,"sha256")
    with tarfile.open(archive,"r:gz") as tf:
        item=tf.getmember(SOURCE_MEMBER)
        if not item.isfile() or item.issym() or item.islnk() or item.size<=0 or item.size>250_000_000:
            raise ValueError("Not a bounded regular source M-R sample member")
        raw=tf.extractfile(item)
        if raw is None:raise ValueError("Missing source member bytes")
        with raw:
            # Deliberately read ONLY the 2 measured columns, not arbitrary code.
            arr=np.loadtxt(raw,usecols=(0,1),dtype=float)
        if arr.ndim!=2 or arr.shape!=(expected_rows,2):
            raise ValueError("Original full M-R sample row count/columns mismatch")
    out=summarize(arr[:,0],arr[:,1],expected_rows)
    out.update({"status":"FULL_ORIGINAL_EQUAL_WEIGHT_MR_POSTERIOR_MEASURED_NOT_EOS_BAYES",
        "source_doi":SOURCE_DOI,"archive_name":archive.name,"archive_size_bytes":archive.stat().st_size,
        "source_archive_md5":md5,"source_archive_sha256":sha,"original_member":SOURCE_MEMBER,
        "source_member_size_bytes":int(item.size),
        "scientific_limitations":["Salmi2024 Amsterdam ST-U GAMMA/NxX M-R equal-weight posterior, not full X-PSI photon likelihood",
          "Posterior includes radio-timing mass prior; do not multiply it as new independent information",
          "These posterior samples must not be multiplied as independent data with Maryland 2024 NICER/XMM results",
          "No EOS Bayes factor or population/selection normalization is calculated"]})
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mr-archive",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    result=audit(a.mr_archive)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding='utf-8')
    print("VERIFIED_FULL_SOURCE",result["source_archive_md5"],"N",result["rows"])
    print("R_16_50_84",*(result["R_quantiles_km"][str(q)] for q in (.16,.5,.84)))
    print("OUTPUT",a.out)


if __name__=="__main__":main()
