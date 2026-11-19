"""Create reproducible SHA-pinned massline witnesses from exact original F38 2D KDE ZIP.
CI may replay narrow 1D numerical integration without reprocessing large observational files;
full F38 2D ZIP and source code are preserved in offline library evidence archive.
"""
from __future__ import annotations
import argparse,base64,hashlib,io,json,sys
from pathlib import Path
import numpy as np
from scipy.stats import truncnorm
from scipy.integrate import simpson
from scipy.interpolate import PchipInterpolator
import recover_native_seven_rotating as rec

def run(root:Path,f38zip:Path,outroot:Path):
 result,_,manifest=rec.load_all(root)
 outroot.mkdir(parents=True,exist_ok=True)
 try:
  sys.path.insert(0,'/mnt/data/eos_finish/library_readback')
  sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'research/j0740/original_seven_inference'))
  import original_seven_fullmass_integral as source
 except ImportError as e:raise RuntimeError('original full 2D F38 python module not accessible') from e
 if rec.sha(f38zip.read_bytes())!=rec.F38_EXPECTED_SHA:raise rec.EvidenceFailure('original F38 bytes wrong')
 import zipfile
 report={'schema':'J0740_ORIGINAL_SEVEN_RNS_ROTATING_MASSLINE_PINNED_REAL_2D_F38_WITNESS_V1',
         'source_2d_F38_archive_SHA256':rec.F38_EXPECTED_SHA,
         'integrator':'scipy.integrate.simpson(grid points 1001)',
         'eos_source_C_artifacts_sha256':{name:a['zip_sha256'] for name,a in manifest['artifacts'].items()},
         'models':{}}
 with zipfile.ZipFile(f38zip) as z:
  surfaces={key:source.load_surface(z,key)[0] for key in rec.SIX_KEYS}
  for label,v in result.items():
   mm=np.asarray(v['source_selected_model_arrays']['mass_msun']);rr=np.asarray(v['source_selected_model_arrays']['radius_eq_km']);interp=PchipInterpolator(mm,rr,extrapolate=False)
   lo=max(rec.MASS_LO,float(mm[0]));hi=min(rec.MASS_HI,float(mm[-1]));m=np.linspace(lo,hi,1001);r=interp(m)
   valid=source.xpsi_source_support(m,r)
   likelihoods=np.stack([np.where(valid,surfaces[key](np.column_stack((m,r))),0) for key in rec.SIX_KEYS]).astype(np.float32)
   buf=io.BytesIO();np.savez_compressed(buf,mass_msun=m.astype(np.float64),radius_eq_km=r.astype(np.float64),relative_likelihood_on_original_F38=np.asarray(likelihoods),support_mask=valid.astype(np.uint8))
   b=buf.getvalue();file=outroot/f'{label}_F38_rotating_massline_witness.npz.base64.txt';file.write_text(base64.b64encode(b).decode()+'\n')
   values=[float(simpson(source.density(m)*likelihoods[i],x=m)) for i in range(6)]
   report['models'][label]={'file':file.name,'decoded_npz_sha256':hashlib.sha256(b).hexdigest(),
     'masses_n':len(m),'observed_likelihood_keys':list(rec.SIX_KEYS),'finite_source_kde_integrals':values,
     'source_rotating_mass_range_msun':[lo,hi],
     'source_C_artifact_zip_sha256':manifest['artifacts'][label]['zip_sha256']}
 (outroot/'F38_rotating_massline_witness_manifest.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
 print(json.dumps({k:{'sha256':v['decoded_npz_sha256'],'bytes':(outroot/v['file']).stat().st_size} for k,v in report['models'].items()},indent=2))
 return report
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--archive-root',type=Path,default=Path(__file__).parent);p.add_argument('--f38-zip',type=Path,required=True);p.add_argument('--output',type=Path,default=Path(__file__).parent/'witness');x=p.parse_args();run(x.archive_root,x.f38_zip,x.output)
