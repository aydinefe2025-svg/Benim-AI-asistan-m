import pathlib,re,json,math,sys
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
def momentum_component_weights(initial_rms,points):
    baseline=np.asarray(initial_rms,dtype=float)
    if points<=0 or baseline.ndim!=1 or not np.isfinite(baseline).all() or np.any(baseline<=0):
        raise ValueError("momentum baseline RMS must be finite and strictly positive for every component")
    return 1/(np.sqrt(points)*baseline)
def estimate_column_scaling(operator,n_probes=8,seed=6901):
    rows,cols=operator.shape
    if n_probes<1:raise ValueError("n_probes must be positive")
    rng=np.random.default_rng(seed);diag=np.zeros(cols)
    for _ in range(n_probes):
        z=rng.choice(np.array([-1.,1.]),size=rows)
        q=operator.rmatvec(z);diag+=q*q
    diag/=n_probes
    if not np.isfinite(diag).all() or np.any(diag<0):
        raise ValueError("column-norm estimate is invalid")
    # Exact zero columns are null directions; the unchanged quadratic damping
    # has its unique minimizer at x_j=0, so remove them from the search space.
    active=diag>0
    scale=np.zeros(cols)
    scale[active]=1/np.sqrt(diag[active])
    if not active.any():raise ValueError("all operator columns are null")
    return scale,active
def right_preconditioned_augmented(operator,scale,damping):
    rows,cols=operator.shape
    def forward(z):
        x=scale*z
        return np.r_[operator.matvec(x),damping*x]
    def adjoint(y):
        return scale*(operator.rmatvec(y[:rows])+damping*y[rows:])
    return LinearOperator((rows+cols,cols),matvec=forward,rmatvec=adjoint,dtype=float)
def check_adj(a,b,label):
    err=abs(a-b)/max(abs(a),abs(b),1e-30)
    assert err<1e-10,(label,a,b,err)
    return err
def tests():
    rng=np.random.default_rng(8615);sh=(9,9,9)
    g=np.broadcast_to(np.eye(3),sh+(3,3)).copy()+.01*sym(rng.normal(size=sh+(3,3)))
    geo=Geometry(g,[.7,.8,.9]);x=rng.normal(size=sh+(3,));y=sym(rng.normal(size=g.shape));v=rng.normal(size=x.shape)
    baseline=np.array([2.,1.,.25]);weights=momentum_component_weights(baseline,4)
    assert np.allclose(weights*baseline,.5)
    try:momentum_component_weights([1.,0.,2.],4)
    except ValueError:pass
    else:raise AssertionError("zero baseline must not be silently normalized")
    dense=np.diag([1e-3,1.,1e3])
    toy=LinearOperator((3,3),matvec=lambda z:dense@z,rmatvec=lambda z:dense.T@z,dtype=float)
    scale,active=estimate_column_scaling(toy,n_probes=4,seed=8616)
    assert np.all(active) and np.allclose(scale,[1e3,1.,1e-3])
    aug=right_preconditioned_augmented(toy,scale,.01)
    z=rng.normal(size=3);toy_rhs=rng.normal(size=6)
    check_adj(np.dot(aug@z,toy_rhs),np.dot(z,aug.rmatvec(toy_rhs)),"right-preconditioned augmented operator")
    target=np.r_[np.ones(3),np.zeros(3)]
    sol=lsmr(aug,target,atol=1e-10,btol=1e-10,maxiter=20)
    recovered=scale*sol[0]
    exact=(dense.T@np.ones(3))/(np.diag(dense)**2+.01**2)
    assert np.allclose(recovered,exact,rtol=1e-8,atol=1e-10),(recovered,exact,sol[1:3])
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
def direct_ricci_controls():
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
    print('DIRECT_RICCI_CONTROLS',json.dumps({'relative_errors_n17_n33':errors,'refinement_ratio':errors[0]/errors[1]}),flush=True)
def lap_ops(geo):
    c=np.einsum('...ij,...kij->...k',geo.gi,geo.ch)
    def lap(u):
        total=np.zeros_like(u)
        for i in range(3):
            for j in range(3):
                second=dd(u,i,i,geo.h) if i==j else d(d(u,j,geo.h),i,geo.h)
                total+=geo.gi[...,i,j]*second
        return total-sum(c[...,i]*d(u,i,geo.h) for i in range(3))
    def adj(y):
        total=np.zeros_like(y)
        for i in range(3):
            for j in range(3):
                weighted=geo.gi[...,i,j]*y
                total+=dd(weighted,i,i,geo.h) if i==j else d(d(weighted,i,geo.h),j,geo.h)
        return total+sum(d(c[...,i]*y,i,geo.h) for i in range(3))
    return lap,adj
def source(g,rho,eps,p,v):
    vc=np.einsum('...ij,...j->...i',g,v);v2=np.einsum('...i,...i->...',v,vc)
    assert np.all(v2<1) and np.all(v2>=-1e-13)
    q=(rho*(1+eps)+p)/(1-v2)
    return q-p,q[...,None]*vc,q,v2
def stencil_domain_controls():
    x=np.arange(17,dtype=float)
    a=x**4
    def D(v):return (-np.roll(v,-2)+8*np.roll(v,-1)-8*np.roll(v,1)+np.roll(v,2))/12
    residual=D(D(a))-12*x**2
    e3=float(np.max(np.abs(residual[3:-3])))
    e4=float(np.max(np.abs(residual[4:-4])))
    e5=float(np.max(np.abs(residual[5:-5])))
    assert e3>1e-3 and e4<1e-10 and e5<1e-10,(e3,e4,e5)
    print('STENCIL_DOMAIN_CONTROL',json.dumps({'radius_each_operator':2,'composed_dependency_radius':4,'trim3_max_abs_error':e3,'trim4_max_abs_error':e4,'trim5_max_abs_error':e5}),flush=True)
def bssn_reconstructed_ricci_scalar(geo):
    # Reconstruct phi, conformal metric, and metric-compatible conformal Gamma
    # from the archived physical ADM metric. This is exact only where the
    # connection-constraint variable equals its metric-derived value.
    g=geo.g
    det=np.linalg.det(g)
    assert np.all(det>0)
    phi=np.log(det)/12
    conformal=g*np.exp(-4*phi)[...,None,None]
    cg=Geometry(conformal,geo.h)
    ci=cg.gi
    gamma=np.einsum('...lm,...klm->...k',ci,cg.ch)
    dphi=[d(phi,j,geo.h) for j in range(3)]
    d2phi=[[d(dphi[j],i,geo.h) for j in range(3)] for i in range(3)]
    hess=np.zeros(g.shape[:-2]+(3,3))
    rbar=np.zeros_like(hess)
    for i in range(3):
        for j in range(3):
            hess[...,i,j]=d2phi[i][j]-sum(cg.ch[...,k,i,j]*dphi[k] for k in range(3))
            first=-.5*sum(ci[...,l,m]*d(d(conformal[...,i,j],m,geo.h),l,geo.h) for l in range(3) for m in range(3))
            second=.5*sum(conformal[...,k,i]*d(gamma[...,k],j,geo.h)+conformal[...,k,j]*d(gamma[...,k],i,geo.h) for k in range(3))
            lower=lambda a,b,c:sum(conformal[...,c,n]*cg.ch[...,n,a,b] for n in range(3))
            third=sum(gamma[...,k]*lower(i,j,k) for k in range(3))
            fourth=sum(ci[...,l,m]*(cg.ch[...,k,l,i]*lower(j,k,m)+cg.ch[...,k,l,j]*lower(i,k,m)) for l in range(3) for m in range(3) for k in range(3))
            fifth=sum(ci[...,l,m]*cg.ch[...,k,i,m]*lower(k,l,j) for l in range(3) for m in range(3) for k in range(3))
            rbar[...,i,j]=first+second+third+fourth+fifth
    lapphi=contract(ci,hess)
    grad2=sum(ci[...,i,j]*dphi[i]*dphi[j] for i in range(3) for j in range(3))
    rphi=-2*hess-2*conformal*lapphi[...,None,None]+4*np.einsum('...i,...j->...ij',np.stack(dphi,axis=-1),np.stack(dphi,axis=-1))-4*conformal*grad2[...,None,None]
    return np.exp(-4*phi)*contract(ci,rbar+rphi)
def bssn_general_metric_equivalence_controls():
    # Independent identity check: conformal BSSN Ricci vs direct physical
    # metric Ricci for a smooth, non-conformally-flat unit-determinant metric.
    errors=[]
    for n in (17,33):
        h=2*np.pi/n;c=np.arange(n)*h
        zz,yy,xx=np.meshgrid(c,c,c,indexing='ij')
        u=.025*np.sin(xx)*np.cos(yy)
        phi=.018*np.cos(zz)+.007*np.sin(xx+yy)
        cb=np.zeros(u.shape+(3,3))
        cb[...,0,0]=np.exp(2*u);cb[...,1,1]=np.exp(-2*u);cb[...,2,2]=1.
        gp=np.exp(4*phi)[...,None,None]*cb
        geo=Geometry(gp,[h]*3)
        direct=ricci_scalar(geo)
        reconstructed=bssn_reconstructed_ricci_scalar(geo)
        errors.append(float(np.linalg.norm(reconstructed-direct)/max(np.linalg.norm(direct),1e-30)))
    ratio=errors[0]/max(errors[1],1e-30)
    assert errors[1]<errors[0] and ratio>3,(errors,ratio)
    print('BSSN_GENERAL_METRIC_EQUIVALENCE',json.dumps({'relative_errors_n17_n33':errors,'refinement_ratio':ratio}),flush=True)
def bssn_scalar_controls():
    errs=[]
    for n in (17,33):
        h=2*np.pi/n;c=np.arange(n)*h
        zz,yy,xx=np.meshgrid(c,c,c,indexing='ij')
        phi=1e-5*np.sin(xx)*np.cos(yy)*np.cos(zz)
        gp=np.broadcast_to(np.eye(3),phi.shape+(3,3)).copy()*np.exp(4*phi)[...,None,None]
        geo=Geometry(gp,[h]*3)
        analytic=np.exp(-4*phi)*(24*phi-8e-10*(np.cos(xx)**2*np.cos(yy)**2*np.cos(zz)**2+np.sin(xx)**2*np.sin(yy)**2*np.cos(zz)**2+np.sin(xx)**2*np.cos(yy)**2*np.sin(zz)**2))
        calc=bssn_reconstructed_ricci_scalar(geo)
        errs.append(float(np.linalg.norm(calc-analytic)/np.linalg.norm(analytic)))
    assert errs[1]<errs[0]/8,errs
    flat=Geometry(np.broadcast_to(np.eye(3),(9,9,9,3,3)).copy(),[1,1,1])
    assert np.max(abs(bssn_reconstructed_ricci_scalar(flat)))==0
    print('BSSN_RECONSTRUCTED_RICCI_CONTROLS',errs,flush=True)
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
def main():
    audit_only='--stencil-audit-only' in sys.argv
    tests();scalar_controls();bssn_scalar_controls();direct_ricci_controls();stencil_domain_controls()
    expected={'gxx','gxy','gxz','gyy','gyz','gzz','kxx','kxy','kxz','kyy','kyz','kzz','rho','eps','press','vel[0]','vel[1]','vel[2]','H','M1','M2','M3'}
    fields={};field_inventory=[]
    # Inventory every HDF5 field file before selecting the ADM/matter fields
    # needed for this reconstruction. Filtering by `expected` here would make
    # any omitted ML_BSSN variables invisible and could falsely certify absence.
    for path in sorted(pathlib.Path('source').rglob('*.xyz.h5')):
        n=path.name.removesuffix('.xyz.h5')
        with h5py.File(path,'r') as f:
            def visit(key,obj):
                if not isinstance(obj,h5py.Dataset) or obj.ndim!=3:return
                m=re.search(r'\bit=(0|128)\s+(.*)',key)
                if not m or not re.search(r'\brl=2\b',m[2]):return
                field_inventory.append({'field_file':n,'dataset_key':key,'iteration':int(m[1])})
                if n not in expected:return
                k=(n,int(m[1]),m[2]);assert k not in fields,k
                fields[k]=(obj[...],np.array(obj.attrs['origin'],float),np.array(obj.attrs['delta'],float))
            f.visititems(visit)
    archive_field_names=sorted({item['field_file'] for item in field_inventory})
    report={'scope':'exhaustive archived HDF5 inventory, stencil-domain audit, and exploratory coupled constraint projection on a fixed background; no evolution or physical certification','candidate_solver_run':not audit_only,'inventory_exhaustive_over_all_xyz_h5_files':True,'archive_field_file_count':len(archive_field_names),'archive_field_files':archive_field_names,'non_expected_field_files':sorted(set(archive_field_names)-expected),'artifact':15177726961,'source_archive_sha256':'c34ef2530dad60bd22e0009b0aa7f298909371023ec94cdde88bfef892d63073','available_hdf5_field_files_and_keys':sorted(field_inventory,key=lambda q:(q['field_file'],q['iteration'],q['dataset_key'])),'patches':[]}
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
        valid_by_trim={}
        for trim in (3,4,5):
            vm=np.zeros(shape,bool);vm[trim:-trim,trim:-trim,trim:-trim]=True;vm&=(z>=-1e-10)
            valid_by_trim[trim]=vm
        valid=valid_by_trim[4]
        dense=r0>1e-8;near=dense.copy()
        for ax in range(3):near|=np.roll(dense,1,ax)|np.roll(dense,-1,ax)
        masks={'inner':valid&dense&(r0>.5*r0.max()),'outer_fluid':valid&dense&(r0<=.5*r0.max()),'surface_atmosphere':valid&near&~dense,'far_atmosphere':valid&~near}
        assert all(np.any(m) for m in masks.values())
        # Force reflection symmetry and compact support of the vector potential.
        # Expand the correction support to the entire stencil-safe interior.
        # Keep a 1.5-coordinate-unit taper only at the outer boundary; the
        # previous r<11.5 compact support left much of the vacuum unconstrained.
        active=np.zeros(shape,bool)
        active[:,5:-5,5:-5]=True
        active[-5:]=False
        active&=(z>=-1e-10)
        support_radius=float(np.max(rad[active]))
        active&=(rad<support_radius)
        taper_width=1.5
        taper=np.clip((support_radius-rad)/taper_width,0,1)
        correction_support={'kind':'full stencil-safe interior with outer radial taper','previous_radial_cutoff':11.5,'support_radius':support_radius,'taper_width':taper_width,'active_points':int(active.sum())}
        active_points_by_region={name:int(np.count_nonzero(active&m)) for name,m in masks.items()}
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
        N=int(active.sum())*3;Q=int(active.sum());P=int(valid.sum())
        def extend_scalar(a):
            u=np.zeros(shape);u[active]=a*taper[active]
            for i,j in pairs:u[i]=u[j]
            return u
        def restrict_scalar(u):
            u=u.copy()
            for i,j in pairs:u[j]+=u[i]
            return u[active]*taper[active]
        Hnative=get('H',128)
        rho,eps,press=[get(f,128) for f in ('rho','eps','press')]
        v=np.stack([get(f'vel[{i}]',128) for i in range(3)],axis=-1)
        g=geo.g
        E,S,q,v2=source(g,rho,eps,press,v)
        R=direct_ricci(geo);H=R+geo.hterm(K)-16*np.pi*E
        stencil_audit={}
        for t,gt,Kt in ((0,geo0,K0),(128,geo,K)):
            rt,et,pt=[get(f,t) for f in ('rho','eps','press')]
            vt=np.stack([get(f'vel[{i}]',t) for i in range(3)],axis=-1)
            Et,_,_,_=source(gt.g,rt,et,pt,vt)
            curvature=direct_ricci(gt)+gt.hterm(Kt)
            matter=16*np.pi*Et
            Ht=curvature-matter
            Hbssn=bssn_reconstructed_ricci_scalar(gt)+gt.hterm(Kt)-matter
            Hnt=get('H',t)
            snapshots={}
            for trim in ((3,4,5) if t==128 else (4,5)):
                vm=valid_by_trim[trim]&(z>=-1e-10)
                regions={'all_valid':vm,'dense':vm&dense,'near_surface':vm&near&~dense,'far_atmosphere':vm&~near}
                snapshots[str(trim)]={}
                for region,mm in regions.items():
                    if not np.any(mm):
                        snapshots[str(trim)][region]={'points':0}
                        continue
                    hi=Ht[mm];hb=Hbssn[mm];hn=Hnt[mm]
                    hi_norm=float(np.linalg.norm(hi));hn_norm=float(np.linalg.norm(hn))
                    dot=float(np.dot(hi,hn));den=max(hn_norm**2,1e-60)
                    alpha=dot/den
                    db=float(np.dot(hb,hn));ab=db/den
                    em=matter[mm];curv=curvature[mm];em2=max(float(np.dot(em,em)),1e-60)
                    cm=float(np.dot(curv-hn,em)/em2)
                    snapshots[str(trim)][region]={
                        'points':int(mm.sum()),
                        'independent_H_rms':float(np.sqrt(np.mean(hi**2))),
                        'archived_native_H_rms':float(np.sqrt(np.mean(hn**2))),
                        'raw_relative_mismatch':float(np.linalg.norm(hi-hn)/max(hn_norm,1e-30)),
                        'best_fit_native_scale':alpha,
                        'shape_correlation':dot/max(hi_norm*hn_norm,1e-60),
                        'best_scaled_relative_mismatch':float(np.linalg.norm(hi-alpha*hn)/max(hn_norm,1e-30)),
                        'bssn_metric_gamma_reconstruction_H_rms':float(np.sqrt(np.mean(hb**2))),
                        'bssn_metric_gamma_raw_relative_mismatch':float(np.linalg.norm(hb-hn)/max(hn_norm,1e-30)),
                        'bssn_metric_gamma_best_scale':ab,
                        'bssn_metric_gamma_best_scaled_mismatch':float(np.linalg.norm(hb-ab*hn)/max(hn_norm,1e-30)),
                        'matter_term_best_fit_coefficient_expected_one':cm,
                        'matter_term_best_fit_residual_relative_to_native':float(np.linalg.norm(curv-cm*em-hn)/max(hn_norm,1e-30))}
            common=valid_by_trim[5]&(z>=-1e-10)
            hc=Ht[common];nc=Hnt[common];dn=max(float(np.linalg.norm(nc))**2,1e-60)
            ac=float(np.dot(hc,nc)/dn)
            snapshots['common_trim5']={'points':int(common.sum()),'best_fit_native_scale':ac,'shape_correlation':float(np.dot(hc,nc)/max(float(np.linalg.norm(hc)*np.linalg.norm(nc)),1e-60)),'raw_relative_mismatch':float(np.linalg.norm(hc-nc)/max(float(np.linalg.norm(nc)),1e-30)),'best_scaled_relative_mismatch':float(np.linalg.norm(hc-ac*nc)/max(float(np.linalg.norm(nc)),1e-30))}
            stencil_audit[str(t)]=snapshots
        common=valid_by_trim[5]&(z>=-1e-10)
        stencil_audit['trim3_trim4_contamination_factor']={
            'trim3_independent_H_rms':stencil_audit['128']['3']['all_valid']['independent_H_rms'],
            'trim4_independent_H_rms':stencil_audit['128']['4']['all_valid']['independent_H_rms'],
            'rms_ratio_trim3_to_trim4':stencil_audit['128']['3']['all_valid']['independent_H_rms']/stencil_audit['128']['4']['all_valid']['independent_H_rms']}
        tr=contract(geo.gi,K);A=K-g*tr[...,None,None]/3
        Amix=np.einsum('...ij,...jk->...ik',geo.gi,A);A2=np.einsum('...ij,...ji->...',Amix,Amix)
        C=-6*geo.mom(A)-32*np.pi*S/(1-v2)[...,None]
        V=-4*R+12*A2-64*np.pi*q*v2/(1-v2)
        grad=geo.hgrad(K);lap,lapadj=lap_ops(geo)
        def rms(a,m):return np.sqrt(np.mean(a[m]**2,axis=0))
        if audit_only:
            row={'patch':patch,'mask_used_for_candidate_analysis':'trim4','stencil_domain_audit':stencil_audit,'candidate_solver_run':False}
            report['patches'].append(row)
            print('STENCIL_ARCHIVE_AUDIT',json.dumps(row,allow_nan=False),flush=True)
            continue
        wm=np.zeros(shape+(3,));wh=np.zeros(shape)
        base={}
        for name,m in masks.items():
            n=int(m.sum())
            b={'points':n,'initial_M_rms':rms(M0,m).tolist(),'pre_M_rms':rms(M,m).tolist(),'pre_H_rms':float(rms(H,m)),'pre_native_H_rms':float(rms(Hnative,m)),'native_H_relative_mismatch':float(np.linalg.norm((H-Hnative)[m])/max(np.linalg.norm(Hnative[m]),1e-30))}
            base[name]=b
            wm[m]=momentum_component_weights(b['initial_M_rms'],n)
            wh[m]=1/(np.sqrt(n)*max(b['pre_H_rms'],1e-7))
        def op(lam):
            def forward(a):
                dk=geo.long(extend(a[:N]));u=extend_scalar(a[N:])
                mv=geo.mom(dk)+C*u[...,None]
                hv=contract(grad,dk)-8*lap(u)+V*u
                return np.r_[(wm*mv)[valid].ravel(),(lam*wh*hv)[valid]]
            def adjoint(a):
                mm=np.zeros(shape+(3,));hh=np.zeros(shape)
                mm[valid]=a[:3*P].reshape(-1,3);hh[valid]=a[3*P:]
                mm*=wm;hh*=lam*wh
                xv=restrict(geo.long_adj(geo.mom_adj(mm)+hh[...,None,None]*grad))
                uv=restrict_scalar(np.sum(C*mm,axis=-1)-8*lapadj(hh)+V*hh)
                return np.r_[xv,uv]
            return LinearOperator((4*P,N+Q),matvec=forward,rmatvec=adjoint,dtype=float)
        rng=np.random.default_rng(69)
        O=op(10.);a=rng.normal(size=N+Q);b=rng.normal(size=4*P)
        err=check_adj(np.dot(O@a,b),np.dot(a,O.rmatvec(b)),'coupled actual adjoint')
        row={'patch':patch,'actual_adjoint_error':err,'active_points':Q,'valid_points':P,'correction_support':correction_support,'active_points_by_region':active_points_by_region,'baseline':base,'candidates':[]}
        wt=np.where(abs(z)<1e-10,1.,2.)*np.prod(h)
        def mass_j(g,sourceS,sourcev2):
            sg=np.sqrt(np.linalg.det(g))
            D=sg*rho/np.sqrt(1-sourcev2)
            J=sg*(x*sourceS[...,1]-y*sourceS[...,0])
            return float(np.sum(wt[valid]*D[valid])),float(np.sum(wt[valid]*J[valid]))
        mass0,j0=mass_j(g,S,v2)
        for lam in (10.,100.):
            O=op(lam);target=np.r_[-(wm*M)[valid].ravel(),-(lam*wh*H)[valid]]
            column_scale,column_active=estimate_column_scaling(O,n_probes=8,seed=6901+int(lam))
            Oscaled=right_preconditioned_augmented(O,column_scale,.01)
            augmented_target=np.r_[target,np.zeros(N+Q)]
            sol=lsmr(Oscaled,augmented_target,damp=0.,atol=1e-7,btol=1e-7,maxiter=4096)
            solution=column_scale*sol[0]
            dk=geo.long(extend(solution[:N]));u=extend_scalar(solution[N:])
            for scale in (1.,.5,.25):
                uu=scale*u;aa=A+scale*dk
                if np.max(abs(uu))>.05:
                    row['candidates'].append({'lambda_H':lam,'scale':scale,'rejected':'conformal perturbation exceeds bound'});continue
                G=g*np.exp(4*uu)[...,None,None]
                Kp=np.exp(-2*uu)[...,None,None]*aa+G*tr[...,None,None]/3
                gp=Geometry(G,h)
                Ep,Sp,qp,vp2=source(G,rho,eps,press,v)
                Hp=direct_ricci(gp)+gp.hterm(Kp)-16*np.pi*Ep
                Mp=gp.mom(Kp)-8*np.pi*Sp
                Hpnative_est=Hnative+Hp-H
                mass,j=mass_j(G,Sp,vp2)
                reg={}
                for name,m in masks.items():
                    b=base[name];mm=rms(Mp,m);hh=float(rms(Hp,m));hn=float(rms(Hpnative_est,m))
                    reg[name]={'M_ratio_to_pre':(mm/np.maximum(b['pre_M_rms'],1e-30)).tolist(),'M_ratio_to_initial':(mm/np.maximum(b['initial_M_rms'],1e-30)).tolist(),'H_ratio_to_pre':hh/max(b['pre_H_rms'],1e-30),'native_plus_independent_delta_H_ratio':hn/max(b['pre_native_H_rms'],1e-30)}
                candidate={'lambda_H':lam,'scale':scale,'lsmr_stop':int(sol[1]),'iterations':int(sol[2]),'reported_maxiter':4096,'preconditioner':'8-probe diagonal right scaling; exact original .01 quadratic damping represented as augmented rows','preconditioner_seed':6901+int(lam),'preconditioner_active_columns':int(column_active.sum()),'preconditioner_null_columns':int((~column_active).sum()),'preconditioner_scale_min_nonzero':float(np.min(column_scale[column_active])),'preconditioner_scale_max':float(np.max(column_scale)),'residual_norm':float(sol[3]),'normal_residual_norm':float(sol[4]),'operator_norm_estimate':float(sol[5]),'condition_number_estimate':float(sol[6]),'solution_norm':float(sol[7]),'max_abs_log_conformal':float(np.max(abs(uu))),'max_trace_difference':float(np.max(abs(contract(gp.gi,Kp)-tr))),'baryon_relative_change_fixed_patch':mass/mass0-1,'matter_J_relative_change_fixed_patch':j/j0-1,'regions':reg,'all_M_improved':all(max(q['M_ratio_to_pre'])<=1+1e-10 for q in reg.values()),'all_H_improved':all(q['H_ratio_to_pre']<=1+1e-10 and q['native_plus_independent_delta_H_ratio']<=1+1e-10 for q in reg.values()),'all_M_below_initial':all(max(q['M_ratio_to_initial'])<=1+1e-10 for q in reg.values())}
                row['candidates'].append(candidate)
                print('COUPLED_CANDIDATE',json.dumps(candidate,allow_nan=False),flush=True)
        row['any_coupled_improvement']=any(c.get('all_M_improved') and c.get('all_H_improved') for c in row['candidates'])
        row['any_initial_M_and_H_gate']=any(c.get('all_M_below_initial') and c.get('all_H_improved') for c in row['candidates'])
        report['patches'].append(row)
    assert report['patches']
    report['physical_stability_certified']=False
    pathlib.Path('evidence/coupled_projection.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('COUPLED_RESULT',json.dumps(report,allow_nan=False),flush=True)
if __name__=='__main__':main()
