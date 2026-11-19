"""F72: independent EOS-table resolution vs spacetime-mesh convergence in direct RNS C.

STRICT SCIENTIFIC SCOPE: ONLY F67/F68 exploratory MPA1 PCHIP cold model.
Original nuclear MPA1 and conditional F69 Fe56 EOS are separate, NOT approved.
None of the output represents NICER X-PSI likelihood or seven-original-EOS Bayes.

F72 retains existing F71 196-row equilibria as a control rather than recomputing
expensive previous models. New C equilibria sample the *same* source F67 cold
EOS at 392 and 784 rows, on both 301x601 and 401x801 RNS spacetime meshes.
All numerical radii are true fixed-target-M and -f direct C output, not mixed
spin results or post hoc interpolation.
"""
from __future__ import annotations
import argparse,hashlib,json,math,sys,shutil
from pathlib import Path
import numpy as np

C=299792458.0
G=6.67430e-11
AMU_G=1.66053906660e-24
SOURCE_SHA='d3c4388ef18ab645d410672da3d886d2b9bda446236c2cc4784024fe3be39f22'
SHA_196='5af6e77740c3af282d30918e69a1794dab84895092209ac850c1e2ed2945ac16'
MODEL='MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL'
TARGET_HZ=346.536369
TARGETS=('2.073','2.250')
GRIDS=('301x601','401x801')
COUNTS=(196,392,784)
MASS_TOL=5e-6
SPIN_TOL=.005
F71_BASELINE_SHA={'301x601':'ba5a12f5417f0b4d994fa17d77edaecf3c6defbd46abba81e4474f8ce06c9113',
                  '401x801':'465c6269e33fee4169a76ac83ca3f86ffbacfb7da8499693944bda81f9eb81c9'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate_tables(f67_path,directory,points=COUNTS,reference_196=None):
    """Copy exact source F68 196 table, audit independently reconstructed last-bit drift.

    Floating point exp/interp can differ by a few ULPs across environments.
    Preserve ORIGINAL source bytes as control; do not mislabel a numerically
    equivalent regenerated 196-point table as byte-for-byte reproduced.
    """
    if sha(f67_path)!=SOURCE_SHA:raise ValueError('F72_F67_SOURCE_SHA_DRIFT')
    x=np.loadtxt(f67_path,dtype=float)
    if x.shape!=(2425,4) or not np.isfinite(x).all():raise ValueError('F72_BAD_F67_TABLE')
    if np.any(x[:,[0,1,3]]<=0) or np.any(x[:,2]<0) or np.any(np.diff(x,axis=0)<=0):
        raise ValueError('F72_BAD_F67_THERMO_MONOTONICITY')
    if any(n<100 or n>2000 for n in points) or len(set(points))!=len(points):
        raise ValueError('F72_EOS_POINTS_UNSAFE_C_2001_ARRAY')
    if 196 in points and (reference_196 is None or sha(reference_196)!=SHA_196):
        raise ValueError('F72_F68_EXACT_196_REFERENCE_SHA_DRIFT')
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    ans={}
    for n in points:
        y=np.linspace(math.log(x[0,0]),math.log(x[-1,0]),n)
        p=np.exp(y)
        e=np.exp(np.interp(y,np.log(x[:,0]),np.log(x[:,1])))
        h=np.interp(y,np.log(x[:,0]),x[:,2])
        nrel=np.exp(np.interp(y,np.log(x[:,0]),np.log(x[:,3])))
        n0=x[0,1]*(C*C/G*1e-3)/AMU_G  # arbitrary n0 proxy, NOT physical baryon mass
        rns=np.column_stack((e*C*C/G*1e-3,p*C**4/G*10,h*(C*100)**2+1,n0*nrel))
        if not np.isfinite(rns).all() or np.any(rns<=0) or np.any(np.diff(rns,axis=0)<=0):
            raise ValueError('F72_BAD_MONOTONE_RNS_TABLE')
        path=directory/f'ALT{n}.rns'
        if n==196:
            regenerated=directory/'F72_regenerated_196_ulp_diagnostic.rns'
            with regenerated.open('w',encoding='ascii',newline='\n') as f:
                f.write(f'{n}\n')
                np.savetxt(f,rns,fmt='%.15e')
            src=np.loadtxt(reference_196,skiprows=1)
            if src.shape!=rns.shape or not np.isfinite(src).all():raise ValueError('F72_BAD_ARCHIVED_CONTROL_196')
            maxreldiff=float(np.max(np.abs(src-rns)/np.maximum(np.abs(src),1e-250)))
            if maxreldiff>1e-14:raise ValueError('F72_NUMERIC_196_NOT_REPRODUCED')
            shutil.copyfile(reference_196,path)
            assert sha(path)==SHA_196
        else:
            with path.open('w',encoding='ascii',newline='\n') as f:
                f.write(f'{n}\n')
                np.savetxt(f,rns,fmt='%.15e')
        digest=sha(path)
        ans[n]={'points':n,'rows':n,'path':str(path),'sha256':digest,
                'source_F67_SHA256':SOURCE_SHA,'source_model':MODEL,
                'n0_definition':'ARBITRARY_REFERENCE_FOR_RNS_NOT_PHYSICAL_M0'}
        if n==196:
            ans[n]['regenerated_196_max_relative_ulp_difference']=maxreldiff
            ans[n]['regenerated_196_sha256']=sha(regenerated)
            ans[n]['original_196_exact_bytes_reused']=True
    return ans


def old_f71_to_record(path,grid):
    """Trust only existing SHA-pinned F71 direct-C models, not a fitted radius."""
    if grid not in F71_BASELINE_SHA or sha(path)!=F71_BASELINE_SHA[grid]:
        raise ValueError('F72_BASELINE_F71_DIRECT_C_SHA_DRIFT')
    a=json.loads(Path(path).read_text())
    if a.get('status')!='TWO_DIRECT_C_MASS_SPIN_EQUILIBRIA_PASS_NOT_CONTINUUM_CERTIFICATE':
        raise ValueError('F72_BAD_F71_BASELINE_STATUS')
    if a.get('grid')!=grid or a.get('source_F70_EOS_sha256')!=SHA_196 or not a.get('not_original_MPA1'):
        raise ValueError('F72_BAD_F71_BASELINE_IDENTITY')
    out={'grid':grid,'eos_points':196,'eos_sha256':SHA_196,'source_model':MODEL,
         'not_original_MPA1':True,'not_F69_Fe56':True,'seven_original_EOS_Bayes':'NOT_RUN',
         'stars':a['stars'], 'source_F71_RNS_binary_sha256':a.get('RNS_C_binary_sha256'),
         'source_F71_raw_json_sha256':sha(path)}
    return out


def run(binary, f67, f68_eos, old_f71, grid, count, output):
    if grid not in GRIDS or count not in (392,784):raise ValueError('F72_ONLY_NEW_EOS_DENSITIES')
    if sha(f68_eos)!=SHA_196:raise ValueError('F72_F68_PINNED_REFERENCE_SHA_DRIFT')
    old=old_f71_to_record(old_f71,grid)
    tab=generate_tables(f67,Path(output).parent,points=(196,count),reference_196=f68_eos)
    if Path(tab[196]['path']).read_bytes()!=Path(f68_eos).read_bytes():
        raise ValueError('F72_PINNED_EOS_CONTROL_NOT_REPRODUCED')
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f70'))
    from f70_spin_matched_rns import mass_spin_root
    doc={'schema':'F72_REAL_RNS_C_TWO_AXIS_EOS_SAMPLING_SPACETIME_V1',
         'grid':grid,'eos_points':count,'eos_sha256':tab[count]['sha256'],
         'source_parent_SHA256':SOURCE_SHA,'source_RNS_196_SHA256':SHA_196,
         'source_model':MODEL,'not_original_MPA1':True,'not_F69_Fe56':True,
         'seven_original_EOS_Bayes':'NOT_RUN','RNS_C_executable_SHA256':sha(binary),
         'target_frequency_hz':TARGET_HZ,'stars':{},'status':'IN_PROGRESS',
         'physical_EOS':'NOT_ESTABLISHED','continuum_error':'NOT_ESTABLISHED',
         'baryonic_mass':'NOT_PHYSICALLY_CALIBRATED'}
    output=Path(output);output.parent.mkdir(exist_ok=True,parents=True)
    def save():output.write_text(json.dumps(doc,sort_keys=True,indent=2,allow_nan=False)+'\n')
    save()
    for mk in TARGETS:
        seed=old['stars'][mk]['direct_C']['central_energy_density_g_cm3']
        star,trace=mass_spin_root(binary,Path(tab[count]['path']),float(mk),seed)
        if star.get('solver_mode')!='RNS_C_AXIS_RATIO_DIRECT' or abs(star['mass_msun']-float(mk))>MASS_TOL or abs(star['spin_hz_reported']-TARGET_HZ)>SPIN_TOL:
            raise ValueError('F72_NEW_REAL_C_MASS_OR_SPIN_FAIL')
        doc['stars'][mk]={'direct_C':{k:star[k] for k in ('mass_msun','spin_hz_reported','radius_eq_km','central_energy_density_g_cm3','axis_ratio','solver_mode')},'outer_root_trace':trace}
        save()
    doc['status']='F72_DIRECT_C_BOTH_STARS_MASS_SPIN_MATCHED_PASS_NUMERICAL_ONLY'
    save();return doc


def compare_eos_spacetime(records,table_info):
    if set(records)!={f'{g}_{n}' for g in GRIDS for n in COUNTS}:
        raise ValueError('F72_EOS_AND_SPACETIME_AXES_INCOMPLETE')
    for key,d in records.items():
        grid,count=key.rsplit('_',1);count=int(count)
        if d.get('grid')!=grid or d.get('eos_points')!=count or d.get('eos_sha256')!=table_info[count]['sha256']:
            raise ValueError('F72_BAD_TABLE_GRID_SOURCE_IDENTITY')
        if d.get('source_model')!=MODEL or d.get('not_original_MPA1') is not True or d.get('not_F69_Fe56') is not True or d.get('seven_original_EOS_Bayes')!='NOT_RUN':
            raise ValueError('F72_ORIGINAL_OR_BAYES_UNSUPPORTED_LABEL')
        if set(d.get('stars',{}))!=set(TARGETS):raise ValueError('F72_STARS_MISSING')
        for mk,record in d['stars'].items():
            s=record.get('direct_C',{})
            if s.get('solver_mode')!='RNS_C_AXIS_RATIO_DIRECT':
                raise ValueError('F72_NOT_A_REAL_DIRECT_C_STAR')
            m=s.get('mass_msun');hz=s.get('spin_hz_reported');r=s.get('radius_eq_km')
            if not all(isinstance(v,(float,int)) and math.isfinite(v) for v in (m,hz,r)):
                raise ValueError('F72_NONFINITE_C_MODEL')
            if abs(m-float(mk))>MASS_TOL or abs(hz-TARGET_HZ)>SPIN_TOL:
                raise ValueError('F72_MASS_OR_SPIN_MISMATCH')
            if not 8<r<20:raise ValueError('F72_BAD_RADIUS')
    output={'schema':'F72_EXACT_TWO_AXIS_DIRECT_RNS_C_CONVERGENCE_DIAGNOSTIC_V1',
           'source_parent_SHA256':SOURCE_SHA,'control_196_sha256':SHA_196,
           'source_label':MODEL,'spacetime_meshes':list(GRIDS),'EOS_node_counts':list(COUNTS),
           'total_separate_direct_stars':len(GRIDS)*len(COUNTS)*len(TARGETS),
           'reused_F71_original_196_row_stars':4,'new_F72_C_stars':8,
           'separately_computed_stars':{},'scientific_status':'EOS_AND_GRID_AXIS_NUMERICAL_DIAGNOSTIC_ONLY',
           'original_MPA1_physical_certification':'NOT_ESTABLISHED',
           'F69_rotating_baryonic_M0':'NOT_RUN','source_native_XPSI':'NOT_RUN',
           'original_seven_EOS_Bayes':'NOT_RUN','continuum_error_bound':'NOT_ESTABLISHED'}
    for mk in TARGETS:
        table={g:{n:records[f'{g}_{n}']['stars'][mk]['direct_C'] for n in COUNTS} for g in GRIDS}
        radii={g:{str(n):table[g][n]['radius_eq_km'] for n in COUNTS} for g in GRIDS}
        axis_eos={g:{'196_to_392_m':1000*(radii[g]['392']-radii[g]['196']),
                     '392_to_784_m':1000*(radii[g]['784']-radii[g]['392']),
                     '196_to_784_m':1000*(radii[g]['784']-radii[g]['196'])} for g in GRIDS}
        axis_spatial={str(n):1000*(radii['401x801'][str(n)]-radii['301x601'][str(n)]) for n in COUNTS}
        out={'R_eq_km_at_each_grid_each_EOS_count':radii,
             'EOS_table_resolution_changes_at_fixed_spacetime_grid_m':axis_eos,
             'spacetime_grid_changes_at_fixed_EOS_count_m':axis_spatial,
             'EOS_resolution_x_spatial_mesh_interaction_m':axis_spatial['784']-axis_spatial['196'],
             'relative_source_model':'NOT_ORIGINAL_MPA1',
             'separate_physical_error_bound':'NOT_ESTABLISHED'}
        output['separately_computed_stars'][mk]=out
    return output


def main():
    a=argparse.ArgumentParser();a.add_argument('--binary',type=Path,required=True)
    a.add_argument('--f67',type=Path,required=True);a.add_argument('--f68-eos',type=Path,required=True)
    a.add_argument('--baseline-f71',type=Path,required=True)
    a.add_argument('--grid',choices=GRIDS,required=True)
    a.add_argument('--points',type=int,choices=(392,784),required=True)
    a.add_argument('--out',type=Path,required=True)
    z=a.parse_args();run(z.binary,z.f67,z.f68_eos,z.baseline_f71,z.grid,z.points,z.out)

if __name__=='__main__':main()
