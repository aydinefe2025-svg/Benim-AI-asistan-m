"""Resume a pinned official PyPI wheel with validated HTTP range downloads."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import subprocess
import sys

root=Path(__file__).resolve().parents[2]
dist=root/'dist'
parts=dist/'cufft-parts'
parts.mkdir(exist_ok=True)
url='https://files.pythonhosted.org/packages/b4/38/36fd800cec8f6e89b7c1576edaaf8076e69ec631644cdbc1b5f2e2b5a9df/nvidia_cufft_cu12-11.3.0.4-py3-none-win_amd64.whl'
size=199356881
expected='6048ebddfb90d09d2707efb1fd78d4e3a77cb3ae4dc60e19aab6be0ece2ae464'
filename='nvidia_cufft_cu12-11.3.0.4-py3-none-win_amd64.whl'
if '--nvjitlink' in sys.argv:
    parts=dist/'nvjitlink-parts'
    parts.mkdir(exist_ok=True)
    url='https://files.pythonhosted.org/packages/89/76/93c1467b1387387440a4d25102d86b7794535449b689f8e2dc22c1c8ff7f/nvidia_nvjitlink_cu12-12.6.85-py3-none-win_amd64.whl'
    size=161908572
    expected='e61120e52ed675747825cdd16febc6a0730537451d867ee58bee3853b1b13d1c'
    filename='nvidia_nvjitlink_cu12-12.6.85-py3-none-win_amd64.whl'
chunk=8*1024*1024
def recover(p,tail,wanted):
    """Recover completed worker output after an interrupted orchestration session."""
    if not tail.exists(): return
    old=p.read_bytes() if p.exists() else b''
    data=tail.read_bytes()
    if not data:
        tail.unlink()
        return
    offset=old.find(data[:min(128,len(data))]) if old else -1
    if offset>=0:
        overlap=min(len(old)-offset,len(data))
        assert old[offset:offset+overlap]==data[:overlap]
        merged=old[:offset]+data
    else:
        merged=old+data
    assert len(merged)<=wanted,(p.name,len(merged),wanted)
    p.write_bytes(merged)
    tail.unlink()
def download(start):
    end=min(start+chunk,size)-1
    p=parts/f'{start:012d}.part'
    recover(p,p.with_suffix('.tail'),end-start+1)
    if p.exists() and p.stat().st_size==end-start+1:
        return p
    # Long transfers on this connection can exceed two minutes. Keep partial
    # bytes and resume the remaining absolute range instead of discarding them.
    for attempt in range(5):
        have=p.stat().st_size if p.exists() else 0
        if have==end-start+1:
            break
        tail=p.with_suffix('.tail')
        r=subprocess.run(['curl.exe','--fail','--silent','--show-error','--max-time','600','--range',f'{start+have}-{end}','--output',str(tail),url])
        if tail.exists():
            recover(p,tail,end-start+1)
        if r.returncode==0:
            break
    assert p.stat().st_size==end-start+1,(start,p.stat().st_size)
    print(f'Completed bytes {start}-{end}',flush=True)
    return p
with ThreadPoolExecutor(max_workers=12) as pool:
    paths=list(pool.map(download,range(0,size,chunk)))
wheel=dist/filename
with wheel.open('wb') as f:
    for p in paths:
        f.write(p.read_bytes())
assert wheel.stat().st_size==size
assert hashlib.sha256(wheel.read_bytes()).hexdigest()==expected
print(filename+' official SHA-256 verified',flush=True)
