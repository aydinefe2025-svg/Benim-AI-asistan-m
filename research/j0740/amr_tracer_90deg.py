"""Independent archive-only composite nodal quadrature and reconstructed tracers."""
import pathlib, re, json, math
import numpy as np
import h5py
from scipy.interpolate import RegularGridInterpolator

def widths(x,h,lo,hi):
    return np.maximum(0,np.minimum(x+h/2,hi)-np.maximum(x-h/2,lo))

def box_weight(coords,h,box):
    w=[widths(x,di,lo,hi) for x,di,(lo,hi) in zip(coords,h,box)]
    return 2*w[2][:,None,None]*w[1][None,:,None]*w[0][None,None,:]

def intersection(a,b):
    return [(max(x[0],y[0]),min(x[1],y[1])) for x,y in zip(a,b)]

def volume(b):
    return 2*math.prod(max(0,hi-lo) for lo,hi in b)

def effective_weights(coords,h,domain,finer=None):
    w=box_weight(coords,h,domain)
    if finer is not None:w-=box_weight(coords,h,intersection(domain,finer))
    assert np.min(w)>=-1e-10
    return np.maximum(w,0)

def rk4(rhs,t0,t1,x,step):
    x=np.array(x,dtype=float)
    t=float(t0)
    while t<t1-1e-11:
        d=min(step,t1-t)
        a=rhs(t,x);b=rhs(t+d/2,x+d*a/2);c=rhs(t+d/2,x+d*b/2);e=rhs(t+d,x+d*c)
        x=x+d*(a+2*b+2*c+e)/6;t+=d
    return x

def controls():
    # Coarse and fine control volumes cover exactly one physical box even when interfaces bisect coarse cells.
    d=[(-4,4),(-4,4),(0,4)]
    c=[np.arange(-4,5.),np.arange(-4,5.),np.arange(0,5.)]
    f=[np.arange(-2,2.01,.5),np.arange(-2,2.01,.5),np.arange(0,2.01,.5)]
    b=[(-2.25,2.25),(-2.25,2.25),(0,2.25)]
    wc=effective_weights(c,[1]*3,d,b);wf=effective_weights(f,[.5]*3,d)
    assert abs(wc.sum()+wf.sum()-volume(d))<1e-10
    assert abs(wf.sum()-volume(b))<1e-10
    assert abs(3*wc.sum()+3*wf.sum()-3*volume(d))<1e-10
    # Naive overlapping quadrature is a negative control.
    assert box_weight(c,[1]*3,d).sum()+wf.sum()>volume(d)
    rhs=lambda t,x:np.array([-0.1*x[1],.1*x[0],0.])
    x=rk4(rhs,0,10,[2,0,1],.1)
    assert np.linalg.norm(x-np.array([2*np.cos(1),2*np.sin(1),1]))<1e-8
    print('SYNTHETIC_CONTROLS_PASS',flush=True)

def currents(g,rho,eps,p,v):
    det=np.linalg.det(g)
    assert np.all(det>0)
    vc=np.einsum('...ij,...j->...i',g,v)
    v2=np.einsum('...i,...i->...',v,vc)
    assert np.all(v2>=-1e-13) and np.all(v2<1)
    W=1/np.sqrt(1-v2);sg=np.sqrt(det)
    return sg*rho*W,sg[...,None]*(rho*(1+eps)+p)[...,None]*(W*W)[...,None]*vc

def grid(shape,o,h,trim):
    a=[o[i]+h[i]*np.arange(shape[2-i]) for i in range(3)]
    k=np.where(a[2]>=-1e-10)[0];assert len(k)>trim+2
    sl=(slice(int(k[0]),len(a[2])-trim),slice(trim,-trim),slice(trim,-trim))
    coords=[a[0][sl[2]],a[1][sl[1]],a[2][sl[0]]]
    assert all(len(x)>2 for x in coords)
    assert abs(coords[2][0])<1e-10
    b=[(float(x[0]-di/2),float(x[-1]+di/2)) for x,di in zip(coords,h)]
    b[2]=(0.,b[2][1])
    return sl,coords,b

def main():
    controls()
    hydro={'gxx','gxy','gxz','gyy','gyz','gzz','rho','eps','press','vel[0]','vel[1]','vel[2]','dens'}
    gauge={'alp','betax','betay','betaz'}
    files={p.name.removesuffix('.xyz.h5'):p for p in pathlib.Path('source').rglob('*.xyz.h5')}
    assert set(files)==hydro|gauge,sorted(files)
    meta={}
    for field,path in files.items():
        with h5py.File(path,'r') as h:
            def visit(n,o):
                if not isinstance(o,h5py.Dataset) or o.ndim!=3:return
                m=re.search(r'\bit=(\d+)\s+(.*)',n)
                if not m or not re.search(r'\btl=0\b',m[2]):return
                l=re.search(r'\brl=(\d+)\b',m[2])
                if not l:return
                key=(field,int(m[1]),int(l[1]))
                assert key not in meta,('multiple components unsupported',key)
                meta[key]=(n,tuple(o.shape),np.array(o.attrs['origin'],float),np.array(o.attrs['delta'],float),m[2])
            h.visititems(visit)
    times=sorted({t for f,t,l in meta if f=='rho' and l==2})
    assert times==list(range(0,196608+1,16384)),times
    physical=[(-192.,192.),(-192.,192.),(0.,192.)]
    geo={}
    for l in range(3):
        _,shape,o,h,_=meta['rho',0,l]
        assert np.allclose(h,3/2**l)
        for trim in (3,4):
            geo[l,trim]=grid(shape,o,h,trim)
    common=intersection(physical,geo[0,4][2])
    primary=intersection(physical,geo[0,3][2])
    cases=[('trim3_available',3,primary),('trim3_common',3,common),('trim4_common',4,common)]
    for name,trim,d in cases:
        assert volume(d)>0
        for l in (1,2):
            assert intersection(geo[l,trim][2],geo[l-1,trim][2])==geo[l,trim][2]
    report={'scope':'composite nodal control-volume quadrature, nested aligned patches, no double counting; matter Jz not global ADM J; reconstructed tracers from sparse Eulerian snapshots not native tracked particles','artifact':15208830686,'analytic_controls':'PASS','domains':{name:{'box':d,'volume':volume(d),'full_physical':d==physical} for name,trim,d in cases},'levels':{str(l):{'shape':meta['rho',0,l][1],'origin':meta['rho',0,l][2].tolist(),'delta':meta['rho',0,l][3].tolist(),'trim3_box':geo[l,3][2],'trim4_box':geo[l,4][2]} for l in range(3)},'snapshots':[]}
    tracers=[]
    for it in times:
        totals={name:dict(baryon=0.,primitive_baryon=0.,dense_baryon=0.,matter_Jz=0.,dense_matter_Jz=0.,volume=0.,dens_error_L1=0.,levels=[]) for name,_,_ in cases}
        for l in range(3):
            _,shape,o,h,patch=meta['rho',it,l]
            _,s0,o0,h0,_=meta['rho',0,l]
            assert shape==s0 and np.array_equal(o,o0) and np.array_equal(h,h0)
            data={}
            for field in hydro|(gauge if l==2 else set()):
                n,ss,oo,hh,pp=meta[field,it,l]
                assert ss==shape and np.array_equal(o,oo) and np.array_equal(h,hh) and pp==patch
                with h5py.File(files[field],'r') as f:data[field]=f[n][...]
                assert np.isfinite(data[field]).all(),(it,l,field)
            for name,trim,d in cases:
                sl,coords,b=geo[l,trim]
                sub={f:a[sl] for f,a in data.items()}
                sh=sub['rho'].shape
                g=np.zeros(sh+(3,3))
                for i,j in [(0,0),(0,1),(0,2),(1,1),(1,2),(2,2)]:
                    g[...,i,j]=g[...,j,i]=sub['g'+'xyz'[i]+'xyz'[j]]
                v=np.stack([sub['vel[%d]'%i] for i in range(3)],axis=-1)
                D,S=currents(g,sub['rho'],sub['eps'],sub['press'],v)
                J=coords[0][None,None,:]*S[...,1]-coords[1][None,:,None]*S[...,0]
                W=effective_weights(coords,h,intersection(d,b),geo[l+1,trim][2] if l<2 else None)
                dense=sub['rho']>1e-8;dens=sub['dens']
                result={'baryon':float(np.sum(W*dens)),'primitive_baryon':float(np.sum(W*D)),'dense_baryon':float(np.sum(W[dense]*dens[dense])),'matter_Jz':float(np.sum(W*J)),'dense_matter_Jz':float(np.sum(W[dense]*J[dense])),'volume':float(W.sum()),'dens_error_L1':float(np.sum(W*np.abs(D-dens)))}
                for k,value in result.items():totals[name][k]+=value
                totals[name]['levels'].append({'rl':l,'positive_weight_points':int(np.count_nonzero(W)),**result})
                if l==2 and name=='trim3_available':
                    vel=np.stack([sub['alp']*sub['vel[%d]'%i]-sub['beta'+'xyz'[i]] for i in range(3)],axis=-1)
                    tracers.append((it*0.75/512,RegularGridInterpolator((coords[2],coords[1],coords[0]),vel,bounds_error=True),RegularGridInterpolator((coords[2],coords[1],coords[0]),sub['rho'],bounds_error=True)))
                del sub,g,v,D,S,J,W
            del data
        for name,trim,d in cases:
            q=totals[name];q['volume_relative_error']=abs(q['volume']/volume(d)-1)
            assert q['volume_relative_error']<1e-12,(name,it,q['volume_relative_error'])
            q['dens_error_relative_L1']=q['dens_error_L1']/abs(q['baryon'])
            assert q['dens_error_relative_L1']<1e-8
        row={'iteration':it,'time':it*0.75/512,'cases':totals}
        report['snapshots'].append(row)
        print('COMPOSITE_SNAPSHOT',json.dumps(row,allow_nan=False),flush=True)
    for row in report['snapshots']:
        for name,_,_ in cases:
            a=report['snapshots'][0]['cases'][name];b=row['cases'][name]
            b['relative_changes']={k:b[k]/a[k]-1 for k in ('baryon','dense_baryon','matter_Jz','dense_matter_Jz')}
    report['max_relative_changes']={name:{k:max(abs(row['cases'][name]['relative_changes'][k]) for row in report['snapshots']) for k in ('baryon','dense_baryon','matter_Jz','dense_matter_Jz')} for name,_,_ in cases}
    # Common physical region isolates interface partition sensitivity.
    report['max_trim_sensitivity_common']={k:max(abs(s['cases']['trim4_common'][k]/s['cases']['trim3_common'][k]-1) for s in report['snapshots']) for k in ('baryon','dense_baryon','matter_Jz','dense_matter_Jz')}
    def advect(snap,seed,step):
        pos=np.array(seed,float);angle=[math.atan2(pos[1],pos[0])];track=[pos.tolist()];minrho=math.inf
        for (t0,u0,r0),(t1,u1,r1) in zip(snap[:-1],snap[1:]):
            def rhs(t,x):
                nonlocal minrho
                pt=np.array([abs(x[2]),x[1],x[0]])
                f=(t-t0)/(t1-t0)
                v=(1-f)*u0(pt).reshape(3)+f*u1(pt).reshape(3)
                density=float(((1-f)*r0(pt)+f*r1(pt)).item());minrho=min(minrho,density)
                if x[2]<0:v[2]*=-1
                if abs(x[2])<1e-12:v[2]=0.
                return v
            pos=rk4(rhs,t0,t1,pos,step);angle.append(math.atan2(pos[1],pos[0]));track.append(pos.tolist())
        degrees=float(np.degrees(np.unwrap(angle)[-1]-angle[0]))
        return {'angle_degrees':degrees,'last_position':pos.tolist(),'min_interpolated_rho':minrho,'all_sampled_rhs_in_fluid':minrho>1e-8,'track':track}
    result=[]
    for radius in (2.,3.,4.):
        for z0 in (0.,1.):
            for phi in (0.,math.pi/2):
                seed=[radius*math.cos(phi),radius*math.sin(phi),z0]
                try:
                    a=advect(tracers,seed,.5);b=advect(tracers,seed,.25);c=advect(tracers[::2],seed,.25)
                    result.append({'seed':seed,'full':b,'max_step_difference_degrees':abs(a['angle_degrees']-b['angle_degrees']),'temporal_subsampling_difference_degrees':abs(c['angle_degrees']-b['angle_degrees']),'position_step_difference':float(np.linalg.norm(np.array(a['last_position'])-b['last_position']))})
                except ValueError as e:result.append({'seed':seed,'failure':str(e)})
    report['reconstructed_tracers']=result
    # Compare all seven common-time spatial diagnostics to the preserved independent 90-degree receipt.
    previous=json.loads(pathlib.Path('reference/amr_tracer.json').read_text())
    assert previous['artifact']==15185720482
    assert len(previous['snapshots'])==7
    paired=[]
    for a,b in zip(previous['snapshots'],report['snapshots'][:7]):
        assert a['iteration']==b['iteration'] and a['time']==b['time']
        for name,_,_ in cases:
            for key in ('baryon','primitive_baryon','dense_baryon','matter_Jz','dense_matter_Jz','volume'):
                x,y=a['cases'][name][key],b['cases'][name][key]
                paired.append({'iteration':a['iteration'],'case':name,'quantity':key,'relative_difference':abs(y-x)/max(abs(x),1e-30)})
    report['paired_90deg_spatial_comparison']={'comparisons':len(paired),'max_relative_difference':max(x['relative_difference'] for x in paired),'all_within_1e_6':all(x['relative_difference']<=1e-6 for x in paired),'rows':paired}
    # Last spatial output is 288, not the final scalar endpoint 293.25.
    report['last_spatial_time']=report['snapshots'][-1]['time']
    report['native_scalar_endpoint']=293.25
    report['tracer_failures']=sum('failure' in t or not t['full']['all_sampled_rhs_in_fluid'] for t in result)
    report['physical_stability_certified']=False
    pathlib.Path('evidence/amr_tracer.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print('AMR_TRACER_RESULT',json.dumps({k:v for k,v in report.items() if k not in ('snapshots',)},allow_nan=False),flush=True)
if __name__=='__main__':main()
