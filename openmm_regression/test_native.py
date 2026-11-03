"""Run scientific assertions against the installed patched native libraries."""
import gc, json, subprocess, sys, os, hashlib
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from pathlib import Path
import numpy as np
import openmm as mm
from openmm import unit as u
from checkpoint_repro import water_box, run
from cpupme_repro import water_box as pme_water, forces
from neighbor_repro import pair_count
root=Path(__file__).resolve().parent
logs=root/'native_results'
logs.mkdir(exist_ok=True)
results=[]
def check(issue, fn):
    try:
        details=fn()
        r=dict(issue=issue,status='PASS',details=details)
    except Exception as e:
        r=dict(issue=issue,status='FAIL',error=repr(e))
    results.append(r)
    print(json.dumps(r),flush=True)
def neighbor():
    rows=[]
    for bx in (0.,1.5,-1.5):
        for eps in (1e-5,1e-8):
            missing=[pair_count('Reference',bx,x,eps)-pair_count('CPU',bx,x,eps) for x in (.5,1.5,2.5,3.5,4.5)]
            rows.append(dict(bx=bx,eps=eps,missing=missing))
            assert not any(missing),rows
    return rows
def checkpoint(platform_name='OpenCL'):
    system, positions=water_box()
    p=mm.Platform.getPlatformByName(platform_name)
    props={'Precision':'single'}
    if 'DeterministicForces' in p.getPropertyNames():
        props['DeterministicForces']='true'
    rows=[]
    for custom in (False,True):
        differ,dx=run(system,positions,p,props,custom)
        rows.append(dict(platform=platform_name,custom=custom,checkpoint_mismatches=len(differ),max_dx=float(dx)))
        assert len(differ)==0 and dx==0,rows
    return rows
def cpupme(platform_name='OpenCL'):
    system,pos=pme_water()
    ref,e_ref=forces(system,pos,'Reference',{})
    gpu,e_gpu=forces(system,pos,platform_name,{'Precision':'single','UseCpuPme':'false'})
    cpu,e_cpu=forces(system,pos,platform_name,{'Precision':'single','UseCpuPme':'true'})
    relative=float(np.max(np.abs(cpu-ref))/np.sqrt(np.mean(ref**2)))
    details=dict(platform=platform_name,reference_energy=e_ref,gpu_energy=e_gpu,cpu_pme_energy=e_cpu,relative_force_error=relative,gpu_cpu_force_delta=float(np.max(np.abs(cpu-gpu))))
    assert relative<1e-3 and abs(e_cpu-e_ref)<1.0,details
    assert not np.array_equal(cpu,gpu),'CPU path not distinguishable from GPU PME'
    # Check force groups and first calculation after updating charges.
    small,xyz=pme_water(n=5,box=2.)
    nb=small.getForce(0)
    nb.setForceGroup(2)
    nb.setReciprocalSpaceForceGroup(5)
    contexts=[]
    for name,props in [('Reference',{}),(platform_name,{'Precision':'single','UseCpuPme':'true'})]:
        c=mm.Context(small,mm.VerletIntegrator(.001),mm.Platform.getPlatformByName(name),props)
        c.setPositions(xyz)
        contexts.append(c)
    def energy(c,groups=-1):
        return c.getState(getEnergy=True,groups=groups).getPotentialEnergy().value_in_unit(u.kilojoule_per_mole)
    all_e=energy(contexts[1])
    split_e=energy(contexts[1],1<<2)+energy(contexts[1],1<<5)
    assert abs(all_e-split_e)<.01,(all_e,split_e)
    assert abs(energy(contexts[1],1<<7))<1e-10
    for i in range(nb.getNumParticles()):
        q,s,e=nb.getParticleParameters(i);nb.setParticleParameters(i,q*.8,s,e)
    for c in contexts: nb.updateParametersInContext(c)
    first=energy(contexts[1]);second=energy(contexts[1]);expected=energy(contexts[0])
    assert abs(first-second)<.01,(first,second)
    assert abs(first-expected)<.5,(first,expected)
    details.update(group_sum_error=abs(all_e-split_e),updated_first_energy=first,updated_second_energy=second,updated_reference_energy=expected)
    return details
def mmcif():
    from openmm_mmcif_roundtrip_regression import roundtrip,waters
    rows=[roundtrip(n,k) for k in (False,True) for n in (26,27,52)]
    assert all(r['status']=='PASS' for r in rows),rows
    return rows
check(5532,mmcif)
def water_check():
    from openmm_mmcif_roundtrip_regression import waters
    r=waters();assert r['status']=='PASS',r
    return r
check(5521,water_check)
check(5515,neighbor)
platforms=[mm.Platform.getPlatform(i).getName() for i in range(mm.Platform.getNumPlatforms())]
gpu_platforms=[name for name in ('OpenCL','CUDA') if name in platforms]
check(5493,lambda:[row for name in gpu_platforms for row in checkpoint(name)])
check(5494,lambda:[cpupme(name) for name in gpu_platforms])
errors=list(mm.Platform.getPluginLoadFailures())
required={'Reference','CPU','OpenCL'}
if (Path(sys.prefix)/'Lib/site-packages/OpenMM.libs/lib/plugins/OpenMMCUDA.dll').exists():
    required.add('CUDA')
out=dict(tests=results,created_utc=datetime.now(timezone.utc).isoformat(),python=sys.version,python_package_version=package_version('openmm'),native_version=mm.Platform.getOpenMMVersion(),source_revision='146a320f97bd4cd7319eaf94f58027d57f5abc7d + native_fixes.patch',platforms=platforms,plugin_errors=errors)
(logs/'summary.json').write_text(json.dumps(out,indent=2)+'\n')
raise SystemExit(any(r['status']!='PASS' for r in results) or bool(errors) or not required.issubset(platforms))

