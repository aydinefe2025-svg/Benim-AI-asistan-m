"""F71: direct 301x601 and 401x801 GR RNS C equilibria, source F70 exact EOS.

Uses F70's proven direct C axis-ratio/frequency + central-density mass root,
not an interpolated radius. The isolated F67/F68 exploratory PCHIP EOS is NOT
physical original MPA1 or F69 Fe56 patch; no X-PSI or EOS Bayes is inferred.
"""
from __future__ import annotations
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'f70'))
from f70_spin_matched_rns import (EOS_SHA,TARGETS,TARGET_HZ,MODEL,SPIN_TOL,MASS_TOL,
                                  sha,validate_f68,mass_spin_root)

GRIDS=('301x601','401x801')

def run(binary, eos, old_fine, grid, out):
    if grid not in GRIDS:raise ValueError('F71_GRID_NOT_ACTUALLY_NEW')
    if sha(eos)!=EOS_SHA:raise ValueError('F71_EOS_SHA_DRIFT')
    validate_f68(old_fine,'201x401')
    d={'schema':'F71_HIGH_RES_DIRECT_C_EQUILIBRIA_SOURCE_LOCKED_V1',
       'source_F70_EOS_sha256':EOS_SHA,'RNS_C_binary_sha256':sha(binary),
       'grid':grid,'source_model':MODEL,'not_original_MPA1':True,
       'not_F69_Fe56':True,'target_frequency_hz':TARGET_HZ,
       'mass_tol_Msun':MASS_TOL,'freq_tol_hz':SPIN_TOL,'stars':{},
       'physical_acceptance':'NOT_ESTABLISHED','EOS_Bayes':'NOT_RUN','status':'IN_PROGRESS'}
    out.parent.mkdir(parents=True,exist_ok=True)
    def write():out.write_text(json.dumps(d,indent=2,sort_keys=True,allow_nan=False)+'\n')
    write()
    for mk in TARGETS:
        seed=old_fine['direct_C_stars'][mk]['rotating']['star']['central_energy_density_g_cm3']
        star,trace=mass_spin_root(binary,eos,float(mk),seed)
        if abs(star['mass_msun']-float(mk))>MASS_TOL or abs(star['spin_hz_reported']-TARGET_HZ)>SPIN_TOL:
            raise ValueError('F71_TWO_CONSTRAINT_ROOT_REJECTED')
        if star['solver_mode']!='RNS_C_AXIS_RATIO_DIRECT':raise ValueError('F71_NO_DIRECT_C')
        d['stars'][mk]={'direct_C':{k:star[k] for k in ('mass_msun','spin_hz_reported','radius_eq_km','central_energy_density_g_cm3','axis_ratio','solver_mode')},
                        'outer_C_root_trace':trace}
        write()
    d['status']='TWO_DIRECT_C_MASS_SPIN_EQUILIBRIA_PASS_NOT_CONTINUUM_CERTIFICATE';write()
    return d

def compare(existing_201,existing_251,new_301,new_401):
    if new_301['grid']!='301x601' or new_401['grid']!='401x801':raise ValueError('F71_HIGH_GRID_LABELS')
    if existing_201['grid']!='201x401' or existing_251['grid']!='251x501':raise ValueError('F71_OLDER_GRID_LABELS')
    series=[existing_201,existing_251,new_301,new_401]
    ans={'schema':'F71_FOUR_HIGHER_MESH_SPATIAL_SEQUENCE_V1','model':MODEL,
         'frequency_hz':TARGET_HZ,'EOS_sha256':EOS_SHA,'stars':{},
         'EOS_Bayes':'NOT_RUN','physical_EOS':'NOT_ESTABLISHED'}
    for doc in series:
        if doc.get('rns_eos_sha256',doc.get('source_F70_EOS_sha256'))!=EOS_SHA:raise ValueError('F71_NOT_IDENTICAL_EOS')
    for mk in TARGETS:
        vals=[]
        for doc in series:
            st=doc['stars'][mk].get('actual_direct_RNS_C_model',doc['stars'][mk].get('direct_C'))
            if not st or abs(st['mass_msun']-float(mk))>MASS_TOL or abs(st['spin_hz_reported']-TARGET_HZ)>SPIN_TOL:
                raise ValueError('F71_MASS_OR_FREQUENCY_DRIFT')
            vals.append(st['radius_eq_km'])
        increments=[1000*(vals[i+1]-vals[i]) for i in range(3)]
        ans['stars'][mk]={'grid_N':[201,251,301,401], 'R_eq_km':vals,'delta_R_m':increments,
                          'last_delta_below_0p25m':abs(increments[-1])<.25,
                          'decrease_last_2':abs(increments[-1])<abs(increments[-2]),
                          'monotone_increment_sign':all(x*y>0 for x,y in zip(increments[:-1],increments[1:]))}
    if all(v['last_delta_below_0p25m'] and v['decrease_last_2'] for v in ans['stars'].values()):
        ans['status']='EMPIRICAL_0p25m_LAST_GRID_STEP_PASS_NOT_PROOF_OF_CONTINUUM_LIMIT'
    else:
        ans['status']='HIGHER_GRID_CHECK_COMPLETE_ASYMPTOTIC_CONVERGENCE_NOT_CERTIFIED'
    return ans

def main():
    a=argparse.ArgumentParser();a.add_argument('--binary',type=Path,required=True)
    a.add_argument('--eos',type=Path,required=True);a.add_argument('--f68',type=Path,required=True)
    a.add_argument('--grid',choices=GRIDS,required=True);a.add_argument('--out',type=Path,required=True)
    z=a.parse_args();run(z.binary,z.eos,json.loads(z.f68.read_text()),z.grid,z.out)
if __name__=='__main__':main()
