import pathlib,re,json,math
import numpy as np,h5py
def d(a,j,h,order):
    ax=2-j
    if order==2:return (np.roll(a,-1,ax)-np.roll(a,1,ax))/(2*h[j])
    return (-np.roll(a,-2,ax)+8*np.roll(a,-1,ax)-8*np.roll(a,1,ax)+np.roll(a,2,ax))/(12*h[j])
def weights(n,h,method):
    w=np.ones(n)
    if method=='trap':w[[0,-1]]=.5;return w*h
    assert (n-1)%2==0
    w[1:-1:2]=4;w[2:-1:2]=2
    return w*h/3
def flux(F,coords,h,L,method):
    idx=[]
    for j,x in enumerate(coords):
        lo=0 if j==2 else -L
        i=np.where((x>=lo-1e-9)&(x<=L+1e-9))[0]
        assert abs(x[i[0]]-lo)<1e-9 and abs(x[i[-1]]-L)<1e-9
        assert i[-1]<len(x)-2
        if j!=2:assert i[0]>=2
        idx.append(i)
    x,y,z=idx
    fx=F[np.ix_(z,y,x)][...,0];fy=F[np.ix_(z,y,x)][...,1];fz=F[np.ix_(z,y,x)][...,2]
    wx,wy,wz=[weights(len(i),di,method) for i,di in zip(idx,h)]
    a=2*np.sum((fx[:,:,-1]-fx[:,:,0])*wz[:,None]*wy[None,:])
    b=2*np.sum((fy[:,-1,:]-fy[:,0,:])*wz[:,None]*wx[None,:])
    c=2*np.sum(fz[-1,:,:]*wy[:,None]*wx[None,:])
    return float(a+b+c),[float(a),float(b),float(c)]
def fields(g,K,coords,h,order):
    gi=np.linalg.inv(g);det=np.linalg.det(g);assert np.all(det>0)
    P=np.einsum('...ij,...jk->...ik',gi,K);tr=np.trace(P,axis1=-2,axis2=-1)
    P-=tr[...,None,None]*np.eye(3)
    phi=np.zeros(g.shape[:-2]+(3,))
    phi[...,0]=-coords[1][None,:,None];phi[...,1]=coords[0][None,None,:]
    J=np.sqrt(det)[...,None]*np.einsum('...ji,...i->...j',P,phi)/(8*np.pi)
    tg=np.trace(g,axis1=-2,axis2=-1)
    mass=np.stack([sum(d(g[...,i,j],j,h,order) for j in range(3))-d(tg,i,h,order) for i in range(3)],axis=-1)/(16*np.pi)
    return mass,J
def controls():
    h=[.25]*3;c=[np.arange(-3,3.01,.25),np.arange(-3,3.01,.25),np.arange(-.75,3.01,.25)]
    z,y,x=np.meshgrid(c[2],c[1],c[0],indexing='ij')
    g=np.broadcast_to(np.eye(3),x.shape+(3,3)).copy()
    K=np.zeros_like(g)
    for order in (2,4):
        a,b=fields(g,K,c,h,order)
        assert flux(a,c,h,2,'simpson')[0]==0 and flux(b,c,h,2,'simpson')[0]==0
        G=g*(1+.001*(x*x+y*y+z*z))[...,None,None]
        a,b=fields(G,K,c,h,order)
        expect=-12*.001*8*2**3/(16*np.pi)
        assert abs(flux(a,c,h,2,'simpson')[0]-expect)<1e-12
    K[...,0,1]=K[...,1,0]=x*x/2
    a,b=fields(g,K,c,h,4)
    assert abs(flux(b,c,h,2,'simpson')[0]-(8/3)*2**5/(8*np.pi))<1e-12
    print('SURFACE_ANALYTIC_CONTROLS_PASS',flush=True)
def main():
    controls()
    required={s+i+j for s in 'gk' for i,j in ('xx','xy','xz','yy','yz','zz')}
    paths={p.name.removesuffix('.xyz.h5'):p for p in pathlib.Path('source').rglob('*.xyz.h5')}
    assert set(paths)==required
    meta={}
    for f,p in paths.items():
        with h5py.File(p,'r') as h:
            def visit(n,o):
                if not isinstance(o,h5py.Dataset) or o.ndim!=3:return
                m=re.search(r'\bit=(\d+)\s+(.*)',n)
                if not m or not re.search(r'\btl=0\b',m[2]):return
                q=re.search(r'\brl=(\d+)\b',m[2])
                if not q:return
                key=(f,int(m[1]),int(q[1]))
                assert key not in meta,key
                meta[key]=(n,o.shape,np.array(o.attrs['origin'],float),np.array(o.attrs['delta'],float),m[2])
            h.visititems(visit)
    times=sorted({t for f,t,l in meta if f=='gxx' and l==0})
    assert times==[0,16384,32768,49152,65536,81920,98304]
    matter=json.loads(pathlib.Path('prior/amr_tracer.json').read_text())
    assert [x['iteration'] for x in matter['snapshots']]==times
    radii={0:[18.,24.,48.,96.,144.],1:[9.,18.,24.],2:[9.]}
    report={'scope':'finite-radius coordinate-cube ADM-like asymptotic mass and axial angular momentum surface diagnostics, not exact global ADM charges or a physical stability certificate','source_artifact':15185720482,'matter_audit_artifact':15189503772,'analytic_controls':'PASS','source_native_mass':2.0732,'source_native_J_geometric':6.06528609337938e48*2.99792458e10/(6.67408e-8*1.98848e33**2),'snapshots':[]}
    for it,previous in zip(times,matter['snapshots']):
        row={'iteration':it,'time':it*.75/512,'matter_Jz_composite':previous['cases']['trim3_available']['matter_Jz'],'baryon_composite':previous['cases']['trim3_available']['baryon'],'surfaces':{}}
        for l in range(3):
            _,shape,o,h,patch=meta['gxx',it,l]
            assert np.allclose(h,3/2**l)
            data={}
            for f in required:
                n,ss,oo,hh,pp=meta[f,it,l]
                assert ss==shape and np.array_equal(o,oo) and np.array_equal(h,hh) and pp==patch
                with h5py.File(paths[f],'r') as a:data[f]=a[n][...]
                assert np.isfinite(data[f]).all()
            g=np.zeros(shape+(3,3));K=np.zeros_like(g)
            for i,j in [(0,0),(0,1),(0,2),(1,1),(1,2),(2,2)]:
                q='xyz'[i]+'xyz'[j]
                g[...,i,j]=g[...,j,i]=data['g'+q]
                K[...,i,j]=K[...,j,i]=data['k'+q]
            del data
            c=[o[i]+h[i]*np.arange(shape[2-i]) for i in range(3)]
            for order in (2,4):
                M,J=fields(g,K,c,h,order)
                for L in radii[l]:
                    key=f'rl{l}_L{L:g}'
                    rec=row['surfaces'].setdefault(key,{'rl':l,'L':L,'dx':float(h[0])})
                    for method in ('trap','simpson'):
                        mv,facesm=flux(M,c,h,L,method);jv,facesj=flux(J,c,h,L,method)
                        rec[f'fd{order}_{method}']={'mass':mv,'Jz':jv,'mass_faces':facesm,'J_faces':facesj}
                del M,J
            del g,K
        report['snapshots'].append(row)
        print('SURFACE_SNAPSHOT',json.dumps(row,allow_nan=False),flush=True)
    initial=report['snapshots'][0]['surfaces']
    report['summary']={}
    for k in initial:
        series=[s['surfaces'][k] for s in report['snapshots']]
        a=initial[k]['fd4_simpson'];z=series[-1]['fd4_simpson']
        out={'initial':a,'last':z}
        for q in ('mass','Jz'):
            out[f'{q}_max_relative_change']=max(abs(s['fd4_simpson'][q]/a[q]-1) for s in series)
            out[f'{q}_max_quadrature_relative_difference']=max(abs(s['fd4_trap'][q]/s['fd4_simpson'][q]-1) for s in series)
            out[f'{q}_max_fd_relative_difference']=max(abs(s['fd2_simpson'][q]/s['fd4_simpson'][q]-1) for s in series)
        report['summary'][k]=out
    report['physical_stability_certified']=False
    pathlib.Path('evidence/adm_surfaces.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('SURFACE_AUDIT',json.dumps({k:v for k,v in report.items() if k!='snapshots'},allow_nan=False),flush=True)
if __name__=='__main__':main()
