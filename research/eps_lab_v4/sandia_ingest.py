"""Download official Sandia data, retain integrity evidence and inspect archive schema.
No inferred pairings, calibration or degradation claims from names alone.
"""
import csv,hashlib,io,json,pathlib,urllib.request,zipfile,collections
BASE='https://data.openei.org/files/8378/'
FILES=('AnonDB.csv','IV.zip','RefIV.zip')
LIMIT=180*1024*1024

def download(name):
    path=pathlib.Path(name);tmp=path.with_suffix(path.suffix+'.part')
    h=hashlib.sha256();size=0
    with urllib.request.urlopen(urllib.request.Request(BASE+name,headers={'User-Agent':'CANO-EPS-Lab/4'}),timeout=45) as f,tmp.open('wb') as out:
        while block:=f.read(1024*1024):
            size+=len(block)
            if size>LIMIT:raise ValueError('size cap exceeded')
            h.update(block);out.write(block)
    tmp.replace(path)
    return path,{'url':BASE+name,'sha256':h.hexdigest(),'bytes':size}

def inspect_zip(p):
    with zipfile.ZipFile(p) as z:
        entries=[x for x in z.infolist() if not x.is_dir()]
        if len({x.filename for x in entries})!=len(entries):raise ValueError('duplicate archive entries')
        if sum(x.file_size for x in entries)>800*1024*1024:raise ValueError('archive expansion limit')
        if z.testzip() is not None:raise ValueError('CRC failure')
        samples=[]
        for x in entries[:5]:
            with z.open(x) as f: raw=f.read(2048)
            samples.append({'name':x.filename,'bytes':x.file_size,'prefix':raw.decode('utf-8',errors='replace')[:1600]})
        return {'members':len(entries),'uncompressed_bytes':sum(x.file_size for x in entries),'extensions':dict(collections.Counter(pathlib.PurePosixPath(x.filename).suffix.lower() for x in entries)),'sample':samples,'all_crc_pass':True,'names':[x.filename for x in entries]}

def main():
    result={'source':'https://data.openei.org/submissions/8378','license':'CC BY 4.0; Sandia National Laboratories','files':{},'status':'INCOMPLETE','limits':'Ingestion and schema inspection only; no confirmed module matching or physical model evaluation.'}
    try:
        for name in FILES:
            p,meta=download(name);result['files'][name]=meta
            if name.endswith('.zip'):meta.update(inspect_zip(p))
            else:
                with p.open(encoding='utf-8-sig',newline='') as f:
                    reader=csv.DictReader(f);rows=list(reader)
                meta.update(columns=reader.fieldnames,rows=len(rows),sample=rows[:3])
            print(name,meta['bytes'],meta['sha256'],flush=True)
        result['status']='SOURCE_DOWNLOADED_CRC_VERIFIED'
    finally:
        pathlib.Path('SANDIA_SOURCE_RECEIPT.json').write_text(json.dumps(result,indent=2,allow_nan=False))
if __name__=='__main__':main()
