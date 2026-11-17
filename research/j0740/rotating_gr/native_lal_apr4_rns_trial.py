"""Build APR4_EPP RNS n-column ablation using actual LALSuite EOS functions, not low-P polytrope.

This is conditional on lalsuite 7.26.16 being source-matched to the pinned
JESTER APR4 table at its first node. It uses LAL EOS energy, pseudoenthalpy,
and RestMassDensityOfPseudoEnthalpy from the SAME EOS.
Physical microphysics is whatever the LAL APR4_EPP model encodes; no claim
that the model uniquely represents nature or EOS Bayes evidence.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from importlib.metadata import version
import numpy as np
import lalsimulation as ls
from apr4_firstlaw_crust import C,G,checksum,SHA_APR4,RHO_CENTER_GCM3,write_rns

UPSTREAM_JESTER='e6768650ce992abfd1153a6833857572fe5cd230'
PIN_LAL_VERSION='7.26.16'


def p_at_native_e(target_e,eos,low,high):
    def energy(p):return float(ls.SimNeutronStarEOSEnergyDensityOfPressureGeometerized(p,eos))
    if not energy(low)<target_e<energy(high):raise ValueError('native EOS energy bracket absent')
    lo,hi=math.log(low),math.log(high)
    for _ in range(90):
        mid=(lo+hi)*.5
        if energy(math.exp(mid))<target_e:lo=mid
        else:hi=mid
    return math.exp(.5*(lo+hi))


def build_tables(source,out_dir,*,points=(196,200),floor_ratio=1e-12,center_upper_ratio=1.08):
    source=Path(source);out_dir=Path(out_dir);out_dir.mkdir(parents=True,exist_ok=True)
    if checksum(source)!=SHA_APR4:raise ValueError('JESTER APR4 source does not match pinned SHA')
    if version('lalsuite')!=PIN_LAL_VERSION:raise ValueError('LALSuite wheel not pinned')
    with np.load(source,allow_pickle=False) as d:
        ps=np.asarray(d['p'],float);es=np.asarray(d['e'],float);ns=np.asarray(d['n'],float);hs=np.asarray(d['h'],float)
    assert len(ps)==865
    mu_geo=float(np.median(es/ns))
    if np.max(np.abs((es/ns)/mu_geo-1))>1e-10:raise ValueError('JESTER n_source not original ε/m_avg approximation')
    eos=ls.SimNeutronStarEOSByName('APR4_EPP')
    p0=float(ps[0]);e0=float(es[0]);h0=float(hs[0]);
    e_lal=float(ls.SimNeutronStarEOSEnergyDensityOfPressureGeometerized(p0,eos))
    h_lal=float(ls.SimNeutronStarEOSPseudoEnthalpyOfPressureGeometerized(p0,eos))
    if abs(e_lal/e0-1)>1e-10 or abs(h_lal-h0)>1e-10:
        raise ValueError('LALSuite package version disagrees with pinned JESTER source at P0')
    center=RHO_CENTER_GCM3*1000*G/C**2
    p_end=p_at_native_e(center*center_upper_ratio,eos,p0,float(ps[-1]))
    p_floor=p0*floor_ratio
    # Read multiple native methods from same EOS. Return native rest-mass rho0_geom.
    def state(p):
        e=float(ls.SimNeutronStarEOSEnergyDensityOfPressureGeometerized(p,eos))
        h=float(ls.SimNeutronStarEOSPseudoEnthalpyOfPressureGeometerized(p,eos))
        dedp=float(ls.SimNeutronStarEOSEnergyDensityDerivOfPressureGeometerized(p,eos))
        rho0=float(ls.SimNeutronStarEOSRestMassDensityOfPseudoEnthalpyGeometerized(h,eos))
        if not all(math.isfinite(x) and x>0 for x in (e,h,dedp,rho0)):
            raise ValueError('Native APR4 p/h/e/rho0 returned invalid physical values')
        return e,h,rho0,1/dedp
    report={
      'status':'NATIVE_LAL_TABLE_SOURCE_VERIFIED_NO_C_GR_YET','schema':'APR4_EPP_LAL_7p26p16_P0_NATIVE_FIRSTLAW_RNS_INPUT_v1',
      'lalsuite_wheel_version':version('lalsuite'),'lalsimulation_module_version':getattr(ls,'__version__','unavailable'),
      'source_pinned_sha256':SHA_APR4,'source_jester_commit':UPSTREAM_JESTER,
      'source_first_node_match':True,'source_first_node':{'p':p0,'e':e0,'h':h0},
      'source_mavg_geom':mu_geo,'native_e_max_over_historical_center':center_upper_ratio,'p_floor_over_JESTER_min':floor_ratio,
      'physical_caveat':'APR4_EPP low-pressure behavior is the LALSuite EOS model; RNS truncates at finite floor P0*1e-12, not analytic P=0. Not a proof the microphysical EOS describes nature.',
      'tables':{}
    }
    for npts in points:
        pp=np.geomspace(p_floor,p_end,npts)
        e=[];h=[];rho=[];cs=[]
        for p in pp:
            a,b,c,d=state(float(p));e.append(a);h.append(b);rho.append(c);cs.append(d)
        ee=np.array(e);hh=np.array(h);rr=np.array(rho);cc=np.array(cs)
        if not all(np.all(np.diff(v)>0) for v in (ee,hh,rr)) or not np.all((cc>0)&(cc<=1)):
            raise ValueError('Native APR4 EOS table fails sampled thermodynamic/causal gate')
        density_cgs=ee*C**2/G*1e-3
        pressure_cgs=pp*C**4/G*10
        enthalpy_cgs=hh*(C*100)**2
        native_baryons_cm3=(rr/mu_geo)/1e6
        approx_baryons_cm3=(ee/mu_geo)/1e6
        rows_native=np.column_stack([density_cgs,pressure_cgs,enthalpy_cgs,native_baryons_cm3])
        rows_approx=np.column_stack([density_cgs,pressure_cgs,enthalpy_cgs,approx_baryons_cm3])
        if not np.array_equal(rows_native[:,:3],rows_approx[:,:3]):raise AssertionError('EOS ablation changed more than n')
        a=out_dir/f'native{npts}.rns';b=out_dir/f'approx{npts}.rns'
        write_rns(a,rows_native);write_rns(b,rows_approx)
        report['tables'][str(npts)]={
          'sha256_native_n':checksum(a),'sha256_approx_n':checksum(b),'npoints':npts,
          'first_three_columns_bitwise_identical':True,
          'p_min':float(pp[0]),'p_max':float(pp[-1]),'h_floor':float(hh[0]),
          'rho0_first_over_source_e_first':float(rr[0]/ee[0]),
          'rho0_center_over_e_center':float(np.interp(math.log(center),np.log(ee),rr)/center),
          'max_native_cs2_sampled':float(cc.max()),'min_native_cs2_sampled':float(cc.min()),
          'native_n_over_approx_at_upper_source':float(rr[-1]/ee[-1]),
          'native_rho_surface_massdensity_gcm3':float(density_cgs[0])}
    report['status']='NATIVE_LAL_APR4_SOURCE_MATCH_AND_TWO_RNS_TABLES_READY'
    out=out_dir/'J0740_NATIVE_LAL_APR4_RNS_TABLES_20261117.json'
    out.write_text(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+'\n')
    print(json.dumps({'status':report['status'],'source_first_node_match':True,'tables':report['tables'],
        'result_sha256':checksum(out),'result_file':str(out)},ensure_ascii=False))
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--npz',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
    o=p.parse_args();build_tables(o.npz,o.out)
if __name__=='__main__':main()
