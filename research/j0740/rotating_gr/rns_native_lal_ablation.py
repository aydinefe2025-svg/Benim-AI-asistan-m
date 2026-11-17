"""Real C/GR APR4_EPP native-LAL baryon-column ablation on two grids."""
from pathlib import Path
import argparse,json,math
from apr4_firstlaw_crust import checksum,RHO_CENTER_GCM3
from native_lal_apr4_rns_trial import build_tables
from rns_firstlaw_baryon_ablation import launch,OBS_SPIN_HZ


def main():
 p=argparse.ArgumentParser();p.add_argument('--npz',required=True,type=Path);p.add_argument('--binary',required=True,type=Path);p.add_argument('--out',required=True,type=Path)
 opt=p.parse_args();opt.out.mkdir(parents=True,exist_ok=True)
 table_info=build_tables(opt.npz,opt.out)
 report={'status':'NATIVE_LAL_GR_NOT_RUN','trial':'Native APR4_EPP low pressure from pinned lalsuite wheel, baryon-only ablation',
         'native_lalsuite_input':table_info,'C_solver_sha256':checksum(opt.binary),
         'central_rho_gcm3':RHO_CENTER_GCM3,'target_spin_hz':OBS_SPIN_HZ,'results':{},
         'caveats':['RNS EOS surface cutoff remains P_floor not literal zero','Native APR4_EPP describes a model, not observationally verified EOS',
         'RNS stdout rounds Mg to .001 Msun, Re to .01 km and spin to .1 Hz','Not fixed-M fixed-spin final rooted model or TOV-Love']}
 out=opt.out/'J0740_NATIVE_LAL_APR4_RNS_C_GR_ABLATION_20261117.json'
 def save():out.write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 save()
 for n in (196,200):
  grid={'npoints':n,'same_first_three_columns':table_info['tables'][str(n)]['first_three_columns_bitwise_identical'],'models':{}}
  report['results'][str(n)]=grid;save()
  for spin in (0.,OBS_SPIN_HZ):
   for label,pth in (('approx',opt.out/f'approx{n}.rns'),('native',opt.out/f'native{n}.rns')):
    try:v=launch(opt.binary,pth,spin,ec=RHO_CENTER_GCM3,timeout=180)
    except Exception as exc:
     report['status']='NATIVE_LAL_GR_NUMERICAL_FAILURE_RETAINED';report['error']={'grid':n,'spin':spin,'label':label,'type':type(exc).__name__,'message':str(exc)[:1800]};save();raise
    grid['models'][f'{spin:.6f}_{label}']=v;save()
   a=grid['models'][f'{spin:.6f}_approx'];b=grid['models'][f'{spin:.6f}_native']
   if any(a[x]!=b[x] for x in ('grav_mass_msun_printed','radius_eq_km_printed','spin_hz_printed')):
    report['status']='NATIVE_LAL_GR_METRIC_PRINT_CHANGED_WITH_ONLY_N';save();raise AssertionError('gravitational field changed in n-only control')
   grid[f'M0_native_minus_approx_percent_spin_{spin:.6f}']=(b['baryonic_mass_msun']/a['baryonic_mass_msun']-1)*100
  save();print('NATIVE_LAL_GR_GRID',n,grid['M0_native_minus_approx_percent_spin_346.536369'],flush=True)
 report['status']='PASS_NATIVE_LAL_SOURCE_MATCHED_C_GR_BARYON_ABLATION_NOT_FINAL_EOS_CERTIFICATION'
 save()
 print(json.dumps({'status':report['status'],'file_sha256':checksum(out),'by_grid':{k:v['M0_native_minus_approx_percent_spin_346.536369'] for k,v in report['results'].items()},'json':str(out)},ensure_ascii=False))
if __name__=='__main__':main()
