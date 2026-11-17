"""PINNED RNS C pilot: same ε(P), h(P), different baryon n(P) at fixed central density.

This is an *ablation* in a trial low-pressure-polytrope APR4 EOS, NOT a
physically certified crust, stellar model, calibrated baryonic mass or EOS Bayes.
Changes to upstream C occur only inside an isolated CI checkout.
"""
from __future__ import annotations
import argparse,hashlib,json,math,re,subprocess,time
from pathlib import Path
from apr4_firstlaw_crust import from_pinned,checksum,write_rns,RHO_CENTER_GCM3

RNS_SHA='97e85d325a33e37f702306414533f6cd77812477'
JESTER_SHA='e6768650ce992abfd1153a6833857572fe5cd230'
OBS_SPIN_HZ=346.536369

FINDMODEL_PATCHES=(
 ('star->enthalpy_min=1.0/(C*C);','star->enthalpy_min=pow(10.0,eos->log_h_tab[1]);'),
 ('star->e_surface=7.8*C*C*KSCALE;','star->e_surface=pow(10.0,eos->log_e_tab[1]);'),
 ('p_surface=1.01e8*KSCALE;','p_surface=pow(10.0,eos->log_p_tab[1]);'))
RNS_OUTPUT_ANCHOR='star.e_center, star.Mass/MSUN, star.R_e*1e-5, star.Omega/(2.0*PI));'
RNS_OUTPUT_INSERT='\n    fprintf(stderr, "J0740_MASS0_MSUN %.9f\\n",star.Mass_0/MSUN);'


def strict_replace(original,before,after):
    if original.count(before)!=1:raise ValueError(f'Pinned C source anchor mismatch: {before}')
    return original.replace(before,after)


def patch_isolated_rns(source_dir):
    source_dir=Path(source_dir)
    patchlog={}
    for file_name in ('findmodel.c','rns.c'):
        file=source_dir/file_name
        raw=file.read_text(encoding='utf-8')
        new=raw
        if file_name=='findmodel.c':
            for a,b in FINDMODEL_PATCHES:new=strict_replace(new,a,b)
        else:
            new=strict_replace(new,RNS_OUTPUT_ANCHOR,RNS_OUTPUT_ANCHOR+RNS_OUTPUT_INSERT)
        file.write_text(new,encoding='utf-8')
        patchlog[file_name]={'sha256_original':hashlib.sha256(raw.encode()).hexdigest(),'sha256_patched':hashlib.sha256(new.encode()).hexdigest()}
    return patchlog


def parse_c_run(stdout,stderr):
    candidates=[]
    for line in stdout.splitlines():
        bits=line.split()
        if len(bits)!=4:continue
        try: vals=[float(v) for v in bits]
        except ValueError:continue
        if all(math.isfinite(v) for v in vals) and vals[0]>0 and .5<vals[1]<3.5 and 5<vals[2]<30 and -0.1<=vals[3]<1000:
            candidates.append(vals)
    if len(candidates)!=1:raise RuntimeError(f'RNS numerical output not unique: {candidates}; stdout tail {stdout[-450:]}')
    masses=re.findall(r'J0740_MASS0_MSUN\s+([0-9eE+.\-]+)',stderr)
    if len(masses)!=1 or not math.isfinite(float(masses[0])):
        raise RuntimeError(f'M0 was not captured independently from C: {stderr[-550:]}')
    ec,m,r,spin=candidates[0]
    return {'e15_approx':ec,'grav_mass_msun_printed':m,'radius_eq_km_printed':r,
            'spin_hz_printed':spin,'baryonic_mass_msun':float(masses[0])}


def launch(binpath,table,spin,ec=RHO_CENTER_GCM3,timeout=180):
    command=[str(Path(binpath).resolve()),'-f','./'+Path(table).name,'-e',f'{ec:.12g}','-s',f'{spin:.9f}']
    p=subprocess.run(command,cwd=str(Path(table).parent),text=True,capture_output=True,timeout=timeout,check=False)
    if p.returncode!=0:raise RuntimeError(f'RNS process failed {p.returncode}: {p.stderr[-1200:]}')
    data=parse_c_run(p.stdout,p.stderr)
    if abs(data['spin_hz_printed']-spin)>0.25:
        raise RuntimeError(f'Spin not within model pilot printed tolerance: {data["spin_hz_printed"]}, target={spin}')
    return data


def run_pilot(binary,source,out):
    c=from_pinned(source)
    target=c.at_e(c.center_e*1.08)
    causal=c.causal_screen(target['p'])
    report={
      'schema':'J0740_RNS_C_APR4_FIRSTLAW_N_ABLATION_P0_POLYTROPE_PILOT_v1',
      'status':'IN_PROGRESS_NOT_PHYSICAL_EOS_CERTIFICATION',
      'rns_commit':RNS_SHA,'jester_commit':JESTER_SHA,
      'source_sha256':checksum(source), 'rns_binary_sha256':checksum(binary),
      'target_spin_hz':OBS_SPIN_HZ,'fixed_central_density_gcm3':RHO_CENTER_GCM3,
      'low_pressure_model':'assumed epsilon(P)=epsilon0*(P/P0)^beta below source Pmin; derivative matched; physically unverified crust',
      'candidate_causality':causal,'max_source_energy_over_center':1.08,
      'differential_test':'same first three RNS tabulated columns bitwise; only n0 fourth column differs',
      'code_path_qualification':'pinned C Findmodel patched only Hmin/Esurface/Psurface to table first knot and rns.c appended stderr M0 printer',
      'results':{},'limitations':['not a unique nuclear-matter crust','not a source-native LALSuite EOS','RNS 0.01 km, 0.001 Msun, 0.1 Hz printed accuracy','not a TOV-Love or EOS Bayesian calculation'],
    }
    j=out/'J0740_APR4_FIRSTLAW_ABLATION_RNS_GR_20261117.json'
    def checkpoint():
        j.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    checkpoint()
    for nrows in (196,200):
        rows,approx,states=c.make_table(target['p'],points=nrows)
        a=out/f'na{nrows}.rns';b=out/f'fl{nrows}.rns'
        write_rns(a,approx);write_rns(b,rows)
        r={'table_SHA256_approx_n':checksum(a),'table_SHA256_firstlaw_n':checksum(b),
          'first_three_columns_identical':bool((approx[:,:3]==rows[:,:3]).all()),'at_same_central':{}}
        if not r['first_three_columns_identical']:raise AssertionError('ablation table changed EOS p/e/h')
        for spin in (0.,OBS_SPIN_HZ):
            for label,path in (('approx_n',a),('firstlaw_n',b)):
                try:
                    rr=launch(binary,path,spin)
                except Exception as exc:
                    report['status']='C_GR_NUMERICAL_PILOT_FAILED_NOT_A_PHYSICAL_CLAIM'
                    report['failure']={'grid':nrows,'spin_hz':spin,'baryon_column':label,'error_type':type(exc).__name__,'message':str(exc)[:1400]}
                    report['results'][str(nrows)]=r
                    checkpoint()
                    raise
                r['at_same_central'][f'{spin:.6f}_{label}']=rr
                report['results'][str(nrows)]=r
                checkpoint()
            old=r['at_same_central'][f'{spin:.6f}_approx_n']
            new=r['at_same_central'][f'{spin:.6f}_firstlaw_n']
            # A *numerical* invariant predicted by C source lineage, not a user guess.
            if any(new[f]!=old[f] for f in ('grav_mass_msun_printed','radius_eq_km_printed','spin_hz_printed')):
                raise AssertionError('Unexpected gravitational/metric output change in n-only ablation')
            if not new['baryonic_mass_msun']<old['baryonic_mass_msun']:
                raise AssertionError('Expected positive baryon-column sensitivity not observed')
            r[f'M0_fraction_change_at_{spin:.6f}']=(new['baryonic_mass_msun']/old['baryonic_mass_msun']-1)
        report['results'][str(nrows)]=r
        checkpoint()
        print('RNS_GRID',nrows,'M0change',r[f'M0_fraction_change_at_{OBS_SPIN_HZ:.6f}'],flush=True)
    report['status']='PASS_NUMERICAL_N_COLUMN_ABLATION_C_GR_NOT_PHYSICAL_CRUST_CERTIFICATION'
    checkpoint()
    print(json.dumps({'status':report['status'],'json':str(j),'SHA256':checksum(j),
      'grid_M0_changes':{k:v[f'M0_fraction_change_at_{OBS_SPIN_HZ:.6f}'] for k,v in report['results'].items()}},ensure_ascii=False))
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--patch',type=Path)
    p.add_argument('--rns',type=Path)
    p.add_argument('--source',type=Path)
    p.add_argument('--out',type=Path)
    a=p.parse_args()
    if a.patch:
        print(json.dumps(patch_isolated_rns(a.patch),indent=2));return
    if not a.rns or not a.source or not a.out:p.error('RNS binary, APR4 source and output required')
    a.out.mkdir(parents=True,exist_ok=True)
    run_pilot(a.rns,a.source,a.out)

if __name__=='__main__':main()
