import pathlib,re,json,math
import numpy as np,h5py
from scipy.sparse.linalg import LinearOperator,lsmr
def d(a,j,h):
    ax=2-j
    return (-np.roll(a,-2,ax)+8*np.roll(a,-1,ax)-8*np.roll(a,1,ax)+np.roll(a,2,ax))/(12*h[j])
def sym(a):return (a+np.swapaxes(a,-1,-2))/2
def contract(a,b):return np.einsum('...ij,...ij->...',a,b)
class Geometry:
    def __init__(self,g,h):
        self.g=g;self.h=h;self.gi=np.linalg.inv(g)
        dg=[d(g,j,h) for j in range(3)]
        ch=np.zeros(g.shape[:-2]+(3,3,3))
        for i in range(3):
            for j in range(3):
                for k in range(3):
                    for l in range(3):ch[...,i,j,k]+=.5*self.gi[...,i,l]*(dg[j][...,l,k]+dg[k][...,l,j]-dg[l][...,j,k])
        self.ch=ch;self.tc=np.einsum('...jjl->...l',ch)
    def long(self,x):
        t=np.stack([d(x,j,self.h) for j in range(3)],axis=-2)-np.einsum('...kij,...k->...ij',self.ch,x)
        q=t+np.swapaxes(t,-1,-2)
        return q-self.g*(contract(self.gi,q)/3)[...,None,None]
    def long_adj(self,y):
        a=y-self.gi*(contract(self.g,y)/3)[...,None,None];a=a+np.swapaxes(a,-1,-2)
        return -sum(d(a[...,j,:],j,self.h) for j in range(3))-np.einsum('...kij,...ij->...k',self.ch,a)
    def mom(self,K):
        q=np.einsum('...ij,...jk->...ik',self.gi,K);tr=np.trace(q,axis1=-2,axis2=-1)
        return sum(d(q[...,j,:],j,self.h) for j in range(3))-np.stack([d(tr,j,self.h) for j in range(3)],axis=-1)+np.einsum('...l,...li->...i',self.tc,q)-np.einsum('...lji,...jl->...i',self.ch,q)
    def mom_adj(self,y):
        a=-np.stack([d(y,j,self.h) for j in range(3)],axis=-2)
        div=sum(d(y[...,j],j,self.h) for j in range(3))
        a+=div[...,None,None]*np.eye(3)
        a+=self.tc[..., :,None]*y[...,None,:]-np.einsum('...lji,...i->...jl',self.ch,y)
        return sym(np.einsum('...ij,...jk->...ik',self.gi,a))
    def hterm(self,K):
        q=np.einsum('...ij,...jk->...ik',self.gi,K)
        return np.trace(q,axis1=-2,axis2=-1)**2-np.einsum('...ij,...ji->...',q,q)
    def hgrad(self,K):
        q=np.einsum('...ij,...jk->...ik',self.gi,K)
        return 2*(np.trace(q,axis1=-2,axis2=-1)[...,None,None]*self.gi-np.einsum('...ij,...jk->...ik',q,self.gi))
def check_adj(a,b,label):
    err=abs(a-b)/max(abs(a),abs(b),1e-30)
    assert err<1e-10,(label,a,b,err)
    return err
def tests():
    rng=np.random.default_rng(8615);sh=(9,9,9)
    g=np.broadcast_to(np.eye(3),sh+(3,3)).copy()+.01*sym(rng.normal(size=sh+(3,3)))
    geo=Geometry(g,[.7,.8,.9]);x=rng.normal(size=sh+(3,));y=sym(rng.normal(size=g.shape));v=rng.normal(size=x.shape)
    l=geo.long(x);assert np.max(abs(contract(geo.gi,l)))<1e-12
    e1=check_adj(np.sum(l*y),np.sum(x*geo.long_adj(y)),'long')
    e2=check_adj(np.sum(geo.mom(y)*v),np.sum(y*geo.mom_adj(v)),'mom')
    K=.01*y;z=.01*sym(rng.normal(size=y.shape));ep=1e-5
    diff=(geo.hterm(K+ep*z)-geo.hterm(K-ep*z))/(2*ep)
    assert np.max(abs(diff-contract(geo.hgrad(K),z)))<1e-11
    # Exact zero for constant vector on flat space.
    flat=Geometry(np.broadcast_to(np.eye(3),g.shape).copy(),[1]*3)
    assert np.max(abs(flat.long(np.ones(x.shape))))==0
    print('PROJECTION_CONTROLS',e1,e2,flush=True)
def main():
    tests()
    expected={'gxx','gxy','gxz','gyy','gyz','gzz','kxx','kxy','kxz','kyy','kyz','kzz','rho','eps','press','vel[0]','vel[1]','vel[2]','H','M1','M2','M3'}
    fields={}
    for path in pathlib.Path('source').rglob('*.xyz.h5'):
        n=path.name.removesuffix('.xyz.h5')
        if n not in expected:continue
        with h5py.File(path,'r') as f:
            def visit(key,obj):
                if not isinstance(obj,h5py.Dataset) or obj.ndim!=3:return
                m=re.search(r'\bit=(0|128)\s+(.*)',key)
                if not m or not re.search(r'\brl=2\b',m[2]):return
                k=(n,int(m[1]),m[2]);assert k not in fields,k
                fields[k]=(obj[...],np.array(obj.attrs['origin'],float),np.array(obj.attrs['delta'],float))
            f.visititems(visit)
    report={'scope':'offline constrained longitudinal correction candidate on archived first-step fields, no evolution, no production correction or certification','artifact':15177726961,'patches':[]}
    for patch in sorted({p for _,_,p in fields}):
        if not all((n,t,patch) in fields for n in expected for t in (0,128)):continue
        r0,o,h=fields['rho',0,patch];shape=r0.shape
        for n in expected:
            for t in (0,128):
                a,oo,hh=fields[n,t,patch];assert a.shape==shape and np.array_equal(o,oo) and np.array_equal(h,hh) and np.isfinite(a).all()
        def get(n,t):return fields[n,t,patch][0]
        def tensor(prefix,t):
            q=np.zeros(shape+(3,3))
            for i,j in ((0,0),(0,1),(0,2),(1,1),(1,2),(2,2)):q[...,i,j]=q[...,j,i]=get(prefix+'xyz'[i]+'xyz'[j],t)
            return q
        def baseline(t):
            g=tensor('g',t);K=tensor('k',t);geo=Geometry(g,h)
            v=np.stack([get(f'vel[{i}]',t) for i in range(3)],axis=-1)
            vc=np.einsum('...ij,...j->...i',g,v);v2=np.einsum('...i,...i->...',v,vc)
            assert np.all(v2<1) and np.all(v2>=-1e-13)
            S=(get('rho',t)*(1+get('eps',t))+get('press',t))/(1-v2)
            return geo,K,geo.mom(K)-8*np.pi*S[...,None]*vc,np.stack([get(f'M{i}',t) for i in (1,2,3)],axis=-1)
        geo0,K0,M0,native0=baseline(0)
        geo,K,M,native=baseline(128)
        zz,yy,xx=np.indices(shape);x=o[0]+h[0]*xx;y=o[1]+h[1]*yy;z=o[2]+h[2]*zz;rad=np.sqrt(x*x+y*y+z*z)
        valid=np.zeros(shape,bool);valid[3:-3,3:-3,3:-3]=True;valid&=(z>=-1e-10)
        dense=r0>1e-8;near=dense.copy()
        for ax in range(3):near|=np.roll(dense,1,ax)|np.roll(dense,-1,ax)
        masks={'inner':valid&dense&(r0>.5*r0.max()),'outer_fluid':valid&dense&(r0<=.5*r0.max()),'surface_atmosphere':valid&near&~dense,'far_atmosphere':valid&~near}
        assert all(np.any(m) for m in masks.values())
        # Force reflection symmetry and compact support of the vector potential.
        active=np.zeros(shape,bool);active[5:-5,5:-5,5:-5]=True
        # Include equatorial plane when ghost depth is <5, but never upper/lateral boundaries.
        active[:,:,:]=False;active[:,5:-5,5:-5]=True;active[-5:]=False
        active&=(z>=-1e-10)&(rad<10)
        taper=np.clip((10-rad)/1.5,0,1)
        parity=np.array([1.,1.,-1.])
        zline=z[:,0,0];pairs=[]
        for iz in np.where(zline< -1e-10)[0]:
            j=int(round((-zline[iz]-o[2])/h[2]))
            if 0<=j<len(zline) and abs(zline[j]+zline[iz])<1e-9:pairs.append((iz,j))
        assert pairs and active.sum()>0
        eq=abs(z)<1e-10
        def extend(a):
            X=np.zeros(shape+(3,));X[active]=a.reshape((-1,3))*taper[active,None];X[...,2][eq]=0
            for i,j in pairs:X[i]=X[j]*parity
            return X
        def restrict(X):
            X=X.copy()
            for i,j in pairs:X[j]+=X[i]*parity
            X[...,2][eq]=0
            return (X[active]*taper[active,None]).ravel()
        N=int(active.sum())*3;P=int(valid.sum());H=get('H',128);grad=geo.hgrad(K)
        def op(lam):
            def forward(a):
                dk=geo.long(extend(a))
                return np.r_[geo.mom(dk)[valid].ravel(),lam*contract(grad,dk)[valid]]
            def adjoint(a):
                m=np.zeros(shape+(3,));m[valid]=a[:3*P].reshape(-1,3)
                hh=np.zeros(shape);hh[valid]=a[3*P:]*lam
                return restrict(geo.long_adj(geo.mom_adj(m)+hh[...,None,None]*grad))
            return LinearOperator((4*P,N),matvec=forward,rmatvec=adjoint,dtype=float)
        rng=np.random.default_rng(21);A=op(10.)
        u=rng.normal(size=N);v=rng.normal(size=4*P)
        adjerr=check_adj(np.dot(A@u,v),np.dot(u,A.rmatvec(v)),'actual masked operator')
        # Use independently reconstructed lower-index ADM momentum, not just Mz.
        rhs=np.r_[-M[valid].ravel(),np.zeros(P)]
        def rms(a,m):return np.sqrt(np.mean(a[m]**2,axis=0))
        base={name:{'points':int(m.sum()),'initial_M_rms':rms(M0,m).tolist(),'pre_M_rms':rms(M,m).tolist(),'pre_H_rms':float(rms(H,m)),'native_pre_M_rms':rms(native,m).tolist(),'independent_vs_native_relative':float(np.linalg.norm((M-native)[m])/max(np.linalg.norm(native[m]),1e-30))} for name,m in masks.items()}
        row={'patch':patch,'adjoint_relative_error':adjerr,'active_vector_points':int(active.sum()),'diagnostic_points':P,'baseline':base,'candidates':[]}
        # Hamiltonian linearized penalty, retained trace and exact nonlinear H change.
        for lam in (10.,100.):
            A=op(lam);sol=lsmr(A,rhs,damp=.001,atol=1e-6,btol=1e-6,maxiter=80)
            dk=geo.long(extend(sol[0]))
            assert np.max(abs(contract(geo.gi,dk)))<1e-10
            dM=geo.mom(dk)
            for scale in (1.,.5,.25,.125):
                kp=K+scale*dk
                Hp=H+geo.hterm(kp)-geo.hterm(K)
                Mp=M+scale*dM
                nn=native+scale*dM
                reg={}
                for name,m in masks.items():
                    b=base[name];mm=rms(Mp,m);hh=float(rms(Hp,m))
                    reg[name]={'M_rms':mm.tolist(),'native_plus_correction_M_rms':rms(nn,m).tolist(),'H_rms':hh,'M_ratio_to_pre':(mm/np.maximum(b['pre_M_rms'],1e-30)).tolist(),'M_ratio_to_initial':(mm/np.maximum(b['initial_M_rms'],1e-30)).tolist(),'H_ratio_to_pre':hh/max(b['pre_H_rms'],1e-30)}
                candidate={'lambda_H':lam,'scale':scale,'lsmr_stop':int(sol[1]),'iterations':int(sol[2]),'residual_norm':float(sol[3]),'delta_K_rms':float(np.sqrt(np.mean((scale*dk[valid])**2))),'max_trace_change':float(np.max(abs(contract(geo.gi,scale*dk)))),'regions':reg,'all_region_M_nonincrease':all(max(q['M_ratio_to_pre'])<=1+1e-10 for q in reg.values()),'all_region_H_nonincrease':all(q['H_ratio_to_pre']<=1+1e-10 for q in reg.values()),'all_region_M_below_initial':all(max(q['M_ratio_to_initial'])<=1+1e-10 for q in reg.values())}
                row['candidates'].append(candidate)
                print('PROJECTION_CANDIDATE',json.dumps(candidate,allow_nan=False),flush=True)
            report['patches'].append(row) if lam==100. else None
        row['any_candidate_all_M_H_nonincrease']=any(q['all_region_M_nonincrease'] and q['all_region_H_nonincrease'] for q in row['candidates'])
    assert report['patches'],'missing matching source fields'
    report['physical_stability_certified']=False
    pathlib.Path('evidence/projection.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('PROJECTION_RESULT',json.dumps(report,allow_nan=False),flush=True)
if __name__=='__main__':main()
