"""Exterior angular-momentum budget from immutable fourth-stage fields.
Coordinate rotations are not exact Killing vectors; no ADM/stability certification.
"""
import json, pathlib, re, numpy as np, h5py
from adm_surface_audit import d, weights, flux

def integral(a,c,h,L):
    ids=[np.flatnonzero((x>=(-L if j<2 else 0)-1e-9)&(x<=L+1e-9)) for j,x in enumerate(c)]
    for j,idx in enumerate(ids):
        assert idx[0]>=2 and idx[-1]<len(c[j])-2
        assert abs(c[j][idx[0]]-(-L if j<2 else 0))<1e-9 and abs(c[j][idx[-1]]-L)<1e-9
    x,y,z=ids
    wx,wy,wz=[weights(len(i),di,'simpson') for i,di in zip(ids,h)]
    return float(2*np.einsum('zyx,z,y,x->',a[np.ix_(z,y,x)],wz,wy,wx,optimize=True))

def budget(g,K,c,h,order,rho,eps,p,v,native):
    gi=np.linalg.inv(g);sg=np.sqrt(np.linalg.det(g))
    assert np.all(np.isfinite(sg)) and np.all(sg>0)
    P=np.einsum('...ij,...jk->...ik',gi,K)
    P-=np.trace(P,axis1=-2,axis2=-1)[...,None,None]*np.eye(3)
    Pu=np.einsum('...ij,...jk->...ik',P,gi)
    Pd=sg[...,None,None]*P
    x=c[0][None,None,:];y=c[1][None,:,None]
    F=(-y[...,None]*Pd[..., :,0]+x[...,None]*Pd[..., :,1])/(8*np.pi)
    geo=np.zeros_like(sg)
    div=np.zeros_like(sg)
    for i,phi in ((0,-y),(1,x)):
        div+=phi*sum(d(Pd[...,j,i],j,h,order) for j in range(3))
        for j in range(3):
            for k in range(j,3):
                geo+=.5*phi*sg*Pu[...,j,k]*d(g[...,j,k],i,h,order)*(1 if j==k else 2)
    # P^j_i partial_j phi^i: d_x phi^y=1, d_y phi^x=-1.
    rot=Pd[...,0,1]-Pd[...,1,0]
    vc=np.einsum('...ij,...j->...i',g,v)
    v2=np.einsum('...i,...i->...',v,vc)
    assert np.all(v2>=-1e-13) and np.all(v2<1)
    S=sg*(rho*(1+eps)+p)/(1-v2)*(-y*vc[...,0]+x*vc[...,1])
    M=(div-geo)/(8*np.pi)-S
    N=None if native is None else sg*(-y*native[...,0]+x*native[...,1])/(8*np.pi)
    G=(geo+rot)/(8*np.pi)
    D=sum(d(F[...,j],j,h,order) for j in range(3))
    out=dict(matter=S,independent_constraint=M,non_killing=G,flux_divergence=D,discrete_product_defect=D-(S+M+G))
    if N is not None:out['native_constraint']=N
    return F,out

def controls():
    c=[np.arange(-3,3.01,.25),np.arange(-3,3.01,.25),np.arange(-.75,3.01,.25)]
    h=[.25]*3; z,y,x=np.meshgrid(c[2],c[1],c[0],indexing='ij')
    g=np.broadcast_to(np.eye(3),x.shape+(3,3)).copy()
    K=np.zeros_like(g);K[...,0,1]=K[...,1,0]=x*x/2
    zero=np.zeros_like(x);v=np.zeros(x.shape+(3,));native=v.copy();native[...,1]=x
    for order in (2,4):
        F,b=budget(g,K,c,h,order,zero,zero,zero,v,native)
        f=flux(F,c,h,2,'simpson')[0]
        assert abs(f-(8/3)*2**5/(8*np.pi))<1e-12
        assert abs(integral(b['independent_constraint'],c,h,2)-f)<1e-12
        assert abs(integral(b['native_constraint'],c,h,2)-f)<1e-12
        assert abs(integral(b['non_killing'],c,h,2))<1e-12
        # Centered FD2 differentiates x^3/2 with an exact +h^2/2 defect;
        # FD4 is exact for this cubic. Test the known defect, not zero for FD2.
        expected_defect=(h[0]**2/2 if order==2 else 0.)*64/(8*np.pi)
        measured_defect=integral(b['discrete_product_defect'],c,h,2)
        assert abs(measured_defect-expected_defect)<1e-12
        assert abs(integral(b['flux_divergence'],c,h,2)-f-expected_defect)<1e-12
        print('POLYNOMIAL_PRODUCT_CONTROL',order,measured_defect,expected_defect,flush=True)
    print('EXTERIOR_BUDGET_ANALYTIC_CONTROLS_PASS',flush=True)

def main():
    controls()
    required={s+i+j for s in 'gk' for i,j in ('xx','xy','xz','yy','yz','zz')}|{'rho','eps','press','vel[0]','vel[1]','vel[2]','M1','M2','M3'}
    files={p.name.removesuffix('.xyz.h5'):p for p in pathlib.Path('source').rglob('*.xyz.h5')}
    native_fields={'M1','M2','M3'}
    required-=native_fields
    present=native_fields & set(files)
    assert present in (set(),native_fields),present
    required|=present
    assert set(files)==required
    meta={}
    for f,p in files.items():
        with h5py.File(p,'r') as a:
            def visit(n,o):
                if not isinstance(o,h5py.Dataset) or o.ndim!=3:return
                m=re.search(r'\bit=(\d+)\s+(.*)',n)
                if not m or not re.search(r'\btl=0\b',m[2]) or not re.search(r'\brl=0\b',m[2]):return
                k=(f,int(m[1]));assert k not in meta
                meta[k]=(n,o.shape,np.array(o.attrs['origin'],float),np.array(o.attrs['delta'],float),m[2])
            a.visititems(visit)
    times=sorted(t for f,t in meta if f=='gxx')
    expected=list(range(311296,400385,16384))
    assert set(expected)<=set(times) and set(times)<=set(expected+[300544,400384]),times
    times=expected
    rows=[]
    for it in times:
        _,shape,o,h,patch=meta['gxx',it];assert np.allclose(h,3)
        data={}
        for f in required:
            n,ss,oo,hh,pp=meta[f,it];assert ss==shape and np.array_equal(o,oo) and np.array_equal(h,hh) and pp==patch
            with h5py.File(files[f],'r') as a:data[f]=a[n][...]
            assert np.isfinite(data[f]).all()
        c=[o[i]+h[i]*np.arange(shape[2-i]) for i in range(3)]
        g=np.zeros(shape+(3,3));K=np.zeros_like(g)
        for i,j in [(0,0),(0,1),(0,2),(1,1),(1,2),(2,2)]:
            q='xyz'[i]+'xyz'[j];g[...,i,j]=g[...,j,i]=data.pop('g'+q);K[...,i,j]=K[...,j,i]=data.pop('k'+q)
        v=np.stack([data.pop('vel[%d]'%i) for i in range(3)],axis=-1)
        N=np.stack([data.pop('M%d'%(i+1)) for i in range(3)],axis=-1) if present else None
        row={'iteration':it,'time':it*.75/512,'orders':{}}
        for order in (2,4):
            F,b=budget(g,K,c,h,order,data['rho'],data['eps'],data['press'],v,N)
            radii=(48,96,144,192)
            surf={L:flux(F,c,h,L,'simpson')[0] for L in radii}
            vol={L:{k:integral(a,c,h,L) for k,a in b.items()} for L in radii}
            out=[]
            for lo,hi in zip(radii[:-1],radii[1:]):
                s=surf[hi]-surf[lo];q={k:vol[hi][k]-vol[lo][k] for k in b}
                q.update(inner=lo,outer=hi,surface_difference=s,surface_minus_volume_divergence=s-q['flux_divergence'],independent_budget_residual=s-q['matter']-q['independent_constraint']-q['non_killing'])
                if present:q.update(native_constraint_disagreement=q['independent_constraint']-q['native_constraint'],native_budget_residual=s-q['matter']-q['native_constraint']-q['non_killing'])
                out.append(q)
            row['orders'][str(order)]={'surfaces':surf,'shells':out}
            del F,b
        rows.append(row)
        print('EXTERIOR_SNAPSHOT',json.dumps(row,allow_nan=False),flush=True)
    report={'scope':'coarse-grid finite-radius axial flux identity, independent constraint and native comparison, non-Killing term, matter and numerical closure; no causal or physical certification','source_artifact':15262477685,'native_3d_constraint_available':bool(present),'native_comparison_status':'computed' if present else 'unavailable: no native 3D M1/M2/M3 in source archive','snapshots':rows,'physical_stability_certified':False}
    pathlib.Path('evidence/exterior_budget.json').write_text(json.dumps(report,indent=2,allow_nan=False))
if __name__=='__main__':main()
