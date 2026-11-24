"""Re-read the cited experimental data.m, pin its Git blob and parse only numeric arrays."""
import hashlib,json, pathlib,re, urllib.request,base64,os
PIN='a25176bacdee211465dd5e0ca340f04a2c14dae8'
URL='https://api.github.com/repos/Yacine-Bouali/Benchmark-Data-for-PV-Parameter-Extraction/git/blobs/'+PIN

def fetch():
    headers={'User-Agent':'CANO-EPS-Lab/4','Accept':'application/vnd.github+json'}
    if os.environ.get('GITHUB_TOKEN'):headers['Authorization']='Bearer '+os.environ['GITHUB_TOKEN']
    with urllib.request.urlopen(urllib.request.Request(URL,headers=headers),timeout=40) as f:d=json.load(f)
    raw=base64.b64decode(d['content']); assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==PIN
    s=raw.decode('utf-8');out={'source':URL,'git_blob_sha1':PIN,'source_sha256':hashlib.sha256(raw).hexdigest(),'devices':{}}
    for k,n in [('RTC',26),('PWP',25)]:
        arrays={}
        for field,key in [('V','V'),('Im','I')]:
            m=re.search(r'\b'+k+r'\.'+field+r'\s*=\s*\[([^\]]+)\]',s,re.S)
            if not m:raise ValueError(f'missing {k}.{field}')
            arrays[key]=[float(x) for x in m.group(1).replace('...',' ').split()]
            assert len(arrays[key])==n
        out['devices'][k]=arrays
    pathlib.Path('benchmark.json').write_text(json.dumps(out,indent=2))
    print('Publisher source Git blob and numerical array counts verified: 26+25.')
if __name__=='__main__':fetch()
