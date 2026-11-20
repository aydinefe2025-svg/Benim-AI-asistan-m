#!/usr/bin/env python3
"""Download and SHA/MD5 audit the OPEN publisher's separate APR(APR) unified EOS.

Not the 12.9 GB already-owned Salmi photon archive and not APR4_EPP.
"""
import hashlib, io, json, pathlib, urllib.request, zipfile, sys
URL='https://zenodo.org/records/15045814/files/APR_APR_unified_crust_nparam_1.zip?download=1'
EXPECTED_MD5='ccc2fbef2b0f51df389ff8f7d9b00608'

def fetch(url=URL):
    req=urllib.request.Request(url,headers={'User-Agent':'J0740-source-repro/1.0 (academic provenance)'})
    with urllib.request.urlopen(req,timeout=90) as res:
        raw=res.read(3_000_000)
    if hashlib.md5(raw).hexdigest()!=EXPECTED_MD5:
        raise RuntimeError('PUBLISHER_SOURCE_MD5_MISMATCH: got '+hashlib.md5(raw).hexdigest())
    return raw

def probe(raw, outdir, expected_md5=EXPECTED_MD5):
    if hashlib.md5(raw).hexdigest()!=expected_md5:
        raise RuntimeError('ORIGINAL_SOURCE_MD5_MISMATCH')
    outdir=pathlib.Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:raise ValueError('ZIP_CRC_ERROR')
        entries=[];relevant={}
        for item in z.infolist():
            if item.is_dir():continue
            contents=z.read(item.filename)
            n=item.filename.rsplit('/',1)[-1]
            e={'name':item.filename,'size':len(contents),'sha256':hashlib.sha256(contents).hexdigest()}
            if n in ('eos.nb','eos.thermo','eos.mr','eos.t','eos.yq'):
                head=contents.decode('utf-8',errors='replace').splitlines()[:5]
                e['first_5_lines']=head
                relevant[n]=contents
                (outdir/n).write_bytes(contents)
            entries.append(e)
    if not all(n in relevant for n in ('eos.nb','eos.thermo')):
        raise RuntimeError('MISSING_COMPOSE_PHYSICS_SOURCE: '+str(list(relevant)))
    nbt=relevant['eos.nb'].decode().split()
    d={'schema':'j0740-F87-actual-publisher-compose-probe-v1','source_url':URL,'publisher':'Zenodo 15045814 / CompOSE EOS 328','source_license':'CC BY 4.0 (publisher landing page)','source_md5':hashlib.md5(raw).hexdigest(),'source_sha256':hashlib.sha256(raw).hexdigest(),'source_bytes':len(raw),'valid_zip_crc':True,'archive_members':entries,'baryon_density_grid_first_tokens':nbt[:9],'status':('REAL_PUBLISHER_SOURCE_DOWNLOADED_AND_EXACT_MD5_VERIFIED' if expected_md5==EXPECTED_MD5 else 'SYNTHETIC_TEST_ONLY')}
    (outdir/'F87_publisher_source_probe.json').write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')
    (outdir/'F87_verified_publisher_original.zip').write_bytes(raw)
    print(json.dumps(d,indent=2,ensure_ascii=False))
    return d

if __name__=='__main__':
    probe(fetch(),sys.argv[1] if len(sys.argv)>1 else 'results/F87')
