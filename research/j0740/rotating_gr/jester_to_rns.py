"""Convert pinned JESTER LALSuite EOS NPZ thermodynamics into RNS tab format.

Purpose: validate actual same-EOS *static* TOV curve against RNS and obtain
independent rotating-GR sequence at the observed J0740 spin. No generic EOS
model posterior evidence is computed.

JESTER npz e,p are geometrized SI length^-2, n stored as physical m^-3,
H is dimensionless; RNS expects density g/cm3, pressure dyn/cm2, enthalpy
cm2/s2 and number density cm^-3. These assumptions must be validated by
matching RNS static masses/radii to the source JESTER TOV curve.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np

G=6.67430e-11
C=299792458.0
DEFAULT_POINTS=196  # RNS manual recommends <= 200


def from_jester_npz(npz_path: Path, *, points: int = DEFAULT_POINTS):
    if not 30<=points<=200:
        raise ValueError("RNS EOS input requires 30–200 points")
    with np.load(npz_path,allow_pickle=False) as data:
        required={'n','p','e','h','masses_EOS','radii_EOS'}
        if not required.issubset(set(data.files)):
            raise ValueError('JESTER EOS missing thermodynamics or static MR source keys')
        n=np.asarray(data['n'],float)
        p=np.asarray(data['p'],float)
        e=np.asarray(data['e'],float)
        h=np.asarray(data['h'],float)
        ms=np.asarray(data['masses_EOS'],float)
        rs=np.asarray(data['radii_EOS'],float)
    if not (n.ndim==1 and n.size>=points and e.shape==p.shape==h.shape==n.shape):
        raise ValueError('Thermodynamic JESTER arrays mismatched')
    if not (ms.ndim==1 and rs.shape==ms.shape and len(ms)>30):
        raise ValueError('JESTER reference mass/radius curve missing')
    if not all(np.all(np.isfinite(x)) and np.all(x>0) for x in (n,p,e)) or not np.all(np.isfinite(h)):
        raise ValueError('Invalid thermodynamic values')
    if not (np.all(np.diff(p)>0) and np.all(np.diff(h)>0)):
        raise ValueError('Physical pressure and enthalpy must increase in source table')
    p_target=np.geomspace(p[0],p[-1],points)
    lnP=np.log(p)
    ln_target=np.log(p_target)
    # For a fixed source table, log-linear thermodynamic interpolation is
    # explicit and rerunnable; no hidden EOS smoothing/refitting.
    e_target=np.exp(np.interp(ln_target,lnP,np.log(e)))
    n_target=np.exp(np.interp(ln_target,lnP,np.log(n)))
    h_target=np.interp(ln_target,lnP,h)
    # RNS H(P)=c^2 int(dp/(e+p)) in cm^2/s^2. JESTER h has a
    # nonzero integration constant; subtract the source lower-bound value.
    density_cgs=e_target * C*C/G * 1e-3
    pressure_cgs=p_target * C**4/G * 10.0
    enthalpy_cgs=(h_target-h_target[0])*(C*100)**2 + 1.0
    baryons_cm3=n_target/1e6
    data=np.column_stack([density_cgs,pressure_cgs,enthalpy_cgs,baryons_cm3])
    if not np.all(np.isfinite(data)) or np.any(data<=0):
        raise ValueError('Invalid RNS data units')
    if not (np.all(np.diff(data[:,1])>0) and np.all(np.diff(data[:,2])>0)):
        raise ValueError('Resampling broke pressure or H monotonicity')
    if not np.all(np.diff(data[:,0])>0):
        raise ValueError('EOS source has non-monotone mass energy density after resampling; DO NOT silently alter it')
    if not np.all(np.diff(data[:,3])>0):
        raise ValueError('EOS source has non-monotone baryon density after resampling; DO NOT silently alter it')
    return data, {'source_points':int(len(n)),'output_points':int(points),
                  'original_EOS_mass_min':float(np.min(ms)),
                  'original_EOS_mass_max':float(np.max(ms)),
                  'source_thermodynamic_e_min_geo':float(e[0]),
                  'source_thermodynamic_p_min_geo':float(p[0]),
                  'jester_lowest_pressure_enthalpy_offset':float(h[0]),
                  'p_range_dyne_cm2':[float(pressure_cgs[0]),float(pressure_cgs[-1])],
                  'density_range_g_cm3':[float(density_cgs[0]),float(density_cgs[-1])],
                  'source_npz_sha256':hashlib.sha256(npz_path.read_bytes()).hexdigest()}


def write_rns(path:Path, rows:np.ndarray):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='ascii',newline='\n') as f:
        f.write(str(len(rows))+'\n')
        np.savetxt(f,rows,fmt='%.15e')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('target',type=Path)
    p.add_argument('--points',type=int,default=DEFAULT_POINTS)
    p.add_argument('--summary',type=Path)
    a=p.parse_args()
    rows,info=from_jester_npz(a.source,points=a.points)
    write_rns(a.target,rows)
    info.update({'rns_table_sha256':hashlib.sha256(a.target.read_bytes()).hexdigest(),
                 'critical_warning':'RNS physical validation must reproduce JESTER static M/R; table conversion alone not evidence'})
    if a.summary:
        a.summary.parent.mkdir(parents=True,exist_ok=True)
        a.summary.write_text(json.dumps(info,indent=2,sort_keys=True)+'\n')
    print(json.dumps(info,indent=2))

if __name__=='__main__':main()
