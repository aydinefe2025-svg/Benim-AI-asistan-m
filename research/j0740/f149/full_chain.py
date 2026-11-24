"""Recover the full published posterior with full compressed archive MD5.
Compare independently published mass-radius sample multiset. No new EOS Bayes."""
import hashlib, json, sys, tarfile, pathlib, shutil, io
import numpy as np
from research.j0740.f144.j0740_archive_input_audit import HashedReader
ROOT='J0740_GAMMA_zenodo/STU/STU_NICER_XMM_hr/STU_outputs/run1_lp40k_Xse001_Dfix/'
BASE='stu_nlive40000_eff0.01_noCONST_noMM_noIS_tol-1'
TARGETS={ROOT+BASE+'post_equal_weights.dat':170471381,
         ROOT+BASE+'stats.dat':2144,ROOT+BASE+'summary.txt':3474}
MR='mr_samples_and_contours/J0740_gamma_NxX_lp40k_se001_mrsamples_post_equal_weights.dat'
def extract(raw,out,targets=TARGETS,md5='7792c92b9ae1fa404ae5bdd3920ce075'):
    out.mkdir(parents=True,exist_ok=True); hashes={}
    reader=HashedReader(raw)
    with tarfile.open(fileobj=reader,mode='r|gz') as tar:
        for m in tar:
            if m.name not in targets: continue
            if m.name in hashes or not m.isfile() or m.size!=targets[m.name]:
                raise ValueError('Unexpected target identity '+m.name)
            p=out/pathlib.PurePosixPath(m.name).name
            h=hashlib.sha256(); n=0
            with p.open('wb') as dst:
                src=tar.extractfile(m)
                for b in iter(lambda:src.read(1048576),b''):
                    h.update(b);n+=len(b);dst.write(b)
            if n!=m.size: raise ValueError('Truncated '+m.name)
            hashes[m.name]={'bytes':n,'sha256':h.hexdigest()}
            print('F149_EXTRACTED',m.name,n,flush=True)
    reader.drain()
    if reader.md5.hexdigest()!=md5 or set(hashes)!=set(targets):
        raise ValueError('Original archive verification failed')
    return hashes
def compare(a,b):
    if a.ndim!=2 or a.shape[1] < 16 or b.ndim!=2 or b.shape[1]!=2:
        raise ValueError('Unexpected chain schema')
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError('Nonfinite posterior')
    if len(a)!=len(b): raise ValueError('Unequal chain lengths')
    x=a[:,:2]; y=b
    def ordered(z): return z[np.lexsort((z[:,1],z[:,0]))]
    delta=np.max(np.abs(ordered(x)-ordered(y)),axis=0)
    return {'shape':list(a.shape),'public_mr_shape':list(b.shape),
            'same_order_exact':bool(np.array_equal(x,y)),
            'same_multiset_exact':bool(np.array_equal(ordered(x),ordered(y))),
            'maximum_sorted_absolute_delta':delta.tolist(),
            'matched_to_1e-7':bool(np.all(delta<=1e-7)),
            'mr_quantiles':np.quantile(x,[.16,.5,.84],axis=0).tolist()}
def main():
    out=pathlib.Path(sys.argv[1]); mr=pathlib.Path(sys.argv[2])
    assert hashlib.md5(mr.read_bytes()).hexdigest()=='ca8e70eeca81feb71321f1a88a24f2f9'
    hashes=extract(sys.stdin.buffer,out)
    a=np.loadtxt(out/(BASE+'post_equal_weights.dat'))
    with tarfile.open(mr) as t:
        names=[x for x in t.getnames() if x.lstrip('./')==MR]
        assert len(names)==1,names
        b=np.loadtxt(t.extractfile(names[0]))
    info=compare(a,b)
    result={'status':'FULL_CHAIN_EXTRACTED_MR_MATCH' if info['matched_to_1e-7'] else 'FULL_CHAIN_EXTRACTED_MR_MISMATCH',
            'archive_md5':'7792c92b9ae1fa404ae5bdd3920ce075',
            'public_mr_archive_md5':'ca8e70eeca81feb71321f1a88a24f2f9','members':hashes,
            'comparison':info,'limitations':'No new likelihood or EOS evidence; verify 15 free-parameter column mapping before using nuisance draws.'}
    (out/'F149_chain_receipt.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
    if not info['matched_to_1e-7']: raise ValueError('Public MR identity not established')
if __name__=='__main__': main()
