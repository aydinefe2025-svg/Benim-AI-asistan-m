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
def ricci_scalar(geo):
    ch=geo.ch;h=geo.h
    ric=sum(d(ch[...,k,:,:],k,h) for k in range(3))
    ric-=np.stack([d(geo.tc,j,h) for j in range(3)],axis=-1)
    ric+=np.einsum('...l,...lij->...ij',geo.tc,ch)-np.einsum('...kjl,...lik->...ij',ch,ch)
    return contract(geo.gi,ric)
def lap_ops(geo):
    c=np.einsum('...ij,...kij->...k',geo.gi,geo.ch)
    def lap(u):
        du=[d(u,i,geo.h) for i in range(3)]
        return sum(geo.gi[...,i,j]*d(du[j],i,geo.h) for i in range(3) for j in range(3))-sum(c[...,i]*du[i] for i in range(3))
    def adj(y):
        return sum(d(d(geo.gi[...,i,j]*y,i,geo.h),j,geo.h) for i in range(3) for j in range(3))+sum(d(c[...,i]*y,i,geo.h) for i in range(3))
    return lap,adj
def source(g,rho,eps,p,v):
    vc=np.einsum('...ij,...j->...i',g,v);v2=np.einsum('...i,...i->...',v,vc)
    assert np.all(v2<1) and np.all(v2>=-1e-13)
    q=(rho*(1+eps)+p)/(1-v2)
    return q-p,q[...,None]*vc,q,v2
def scalar_controls():
    rng=np.random.default_rng(405)
    g=np.broadcast_to(np.eye(3),(9,9,9,3,3)).copy()+.01*sym(rng.normal(size=(9,9,9,3,3)))
    geo=Geometry(g,[.7,.8,.9]);lap,adj=lap_ops(geo)
    a=rng.normal(size=(9,9,9));b=rng.normal(size=a.shape)
    check_adj(np.sum(lap(a)*b),np.sum(a*adj(b)),'scalar covariant laplacian')
    flat=Geometry(np.broadcast_to(np.eye(3),g.shape).copy(),[1]*3)
    assert np.max(abs(ricci_scalar(flat)))==0
    assert np.max(abs(lap_ops(flat)[0](np.ones(a.shape))))==0
    # Continuum conformal H variation on flat periodic low-frequency field:
    # residual converges toward the analytical linear expression with refinement.
    errors=[]
    for n in (17,33):
        h=2*np.pi/n;c=np.arange(n)*h
        zz,yy,xx=np.meshgrid(c,c,c,indexing='ij')
        u=1e-5*np.sin(xx)*np.cos(yy)*np.cos(zz)
        gp=np.broadcast_to(np.eye(3),u.shape+(3,3)).copy()*np.exp(4*u)[...,None,None]
        exact=np.exp(-4*u)*(24*u-8*1e-10*(np.cos(xx)**2*np.cos(yy)**2*np.cos(zz)**2+np.sin(xx)**2*np.sin(yy)**2*np.cos(zz)**2+np.sin(xx)**2*np.cos(yy)**2*np.sin(zz)**2))
        R=ricci_scalar(Geometry(gp,[h]*3))
        errors.append(float(np.linalg.norm(R-exact)/np.linalg.norm(exact)))
    assert errors[1]<errors[0]/8,errors
    print('COUPLED_SCALAR_CONTROLS',errors,flush=True)
def dd(a,i,j,h):
    if i!=j:return d(d(a,i,h),j,h)
    ax=2-i
    return (-np.roll(a,-2,ax)+16*np.roll(a,-1,ax)-30*a+16*np.roll(a,1,ax)-np.roll(a,2,ax))/(12*h[i]**2)
def direct_ricci(geo):
    g,gi,ch,h=geo.g,geo.gi,geo.ch,geo.h
    dg=[d(g,i,h) for i in range(3)]
    di=[-np.einsum('...ia,...ab,...bj->...ij',gi,q,gi) for q in dg]
    low=np.einsum('...lk,...kij->...lij',g,ch)
    r=np.zeros(g.shape)
    for i in range(3):
        for j in range(3):
            for k in range(3):
                for l in range(3):
                    r[...,i,j]+=di[k][...,k,l]*low[...,l,i,j]-di[j][...,k,l]*low[...,l,i,k]
                    r[...,i,j]+=.5*gi[...,k,l]*(dd(g[...,l,j],k,i,h)+dd(g[...,l,i],k,j,h)-dd(g[...,i,j],k,l,h)-dd(g[...,l,k],j,i,h)-dd(g[...,l,i],j,k,h)+dd(g[...,i,k],j,l,h))
    r+=np.einsum('...l,...lij->...ij',geo.tc,ch)-np.einsum('...kjl,...lik->...ij',ch,ch)
    return contract(gi,r)
def ricci_controls():
    errors=[]
    for n in (17,33):
        h=2*np.pi/n;c=np.arange(n)*h
        z,y,x=np.meshgrid(c,c,c,indexing='ij');u=.01*np.sin(x)*np.cos(y)*np.cos(z)
        g=np.exp(4*u)[...,None,None]*np.eye(3)
        du2=.0001*(np.cos(x)**2*np.cos(y)**2*np.cos(z)**2+np.sin(x)**2*np.sin(y)**2*np.cos(z)**2+np.sin(x)**2*np.cos(y)**2*np.sin(z)**2)
        exact=np.exp(-4*u)*(24*u-8*du2)
        v=direct_ricci(Geometry(g,[h]*3))
        errors.append(float(np.linalg.norm(v-exact)/np.linalg.norm(exact)))
    assert errors[1]<errors[0]/8,errors
    print('DIRECT_RICCI_CONTROLS',errors,flush=True)
def main():
    tests();scalar_controls();ricci_controls()
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
    report={'scope':'archived native Hamiltonian compared with nested and direct fourth-order ADM curvature operators; no projection or certification','artifact':15177726961,'patches':[]}
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
        row={'patch':patch,'times':{}}
        for t,G,C in [(0,geo0,K0),(128,geo,K)]:
            v=np.stack([get(f'vel[{i}]',t) for i in range(3)],axis=-1)
            E,_,_,_=source(G.g,get('rho',t),get('eps',t),get('press',t),v)
            R0=ricci_scalar(G);R1=direct_ricci(G)
            h0=R0+G.hterm(C)-16*np.pi*E;h1=R1+G.hterm(C)-16*np.pi*E;native=get('H',t)
            out={}
            for trim in (4,6):
                inside=np.zeros(shape,bool);inside[trim:-trim,trim:-trim,trim:-trim]=True
                for name,m in masks.items():
                    m=m&inside
                    if not m.any():continue
                    def rms(a):return float(np.sqrt(np.mean(a[m]**2)))
                    out[f'{name}_trim{trim}']={'points':int(m.sum()),'native_H':rms(native),'nested_H':rms(h0),'direct_H':rms(h1),'nested_error':rms(h0-native),'direct_error':rms(h1-native),'ricci_difference':rms(R1-R0)}
            row['times'][str(t)]=out
        report['patches'].append(row)
    assert report['patches']
    pathlib.Path('evidence/hamiltonian_operator_audit.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('HAMILTONIAN_OPERATOR_AUDIT',json.dumps(report,allow_nan=False),flush=True)
if __name__=='__main__':main()
