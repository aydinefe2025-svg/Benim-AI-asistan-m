"""Conservative RNS p_at_h/h_at_p surface-bin repair for *truncated* EOS.

The pre-existing JESTER->RNS conversion rebases H(P_min)=1 cm^2/s^2;
RNS uses a truncated surface H_min=1/c^2 in geometrized units.
The 4-point cubic log(H) interpolation is extremely ill-conditioned at the
first bin because H[1]/H[0]~5e16. Repair ONLY that first H/P bin by using
an explicit monotone linear relation of H to log(P), the same representation
used to resample the source h(log(P)). Leave C/GR, P(e), EOS >first bin intact.

This is a numerical-method sensitivity test, NOT a correction to source EOS
physics, zero-pressure outer crust, or EOS Bayesian model evidence.
"""
from __future__ import annotations
import argparse,hashlib,math
from pathlib import Path
import numpy as np

START_P = '''double p_at_h(double hh, 
              double log_p_tab[2001], 
              double log_h_tab[2001],
              int    n_tab, 
              int    *n_nearest_pt)
{
 return pow(10.0,interp(log_h_tab,log_p_tab,n_tab,log10(hh), n_nearest_pt));
}'''
START_H = '''double h_at_p(double pp, 
              double log_h_tab[2001], 
              double log_p_tab[2001],
              int    n_tab, 
              int    *n_nearest_pt)
{
 return pow(10.0,interp(log_p_tab,log_h_tab,n_tab,log10(pp), n_nearest_pt));
}'''
REPLACEMENT_P = '''double p_at_h(double hh, 
              double log_p_tab[2001], 
              double log_h_tab[2001],
              int    n_tab, 
              int    *n_nearest_pt)
{
 /* J0740 bounded first EOS bin: monotone H(logP) exactly inverted. */
 if (hh > 0.0 && hh <= pow(10.0,log_h_tab[2])) {
   double h0=pow(10.0,log_h_tab[1]);
   double h1=pow(10.0,log_h_tab[2]);
   if (!(h1>h0) || !(log_p_tab[2]>log_p_tab[1])) {
     fprintf(stderr,"J0740 boundary H/P not strictly monotone\\n");
     exit(2);
   }
   double u=(hh-h0)/(h1-h0);
   if (u<0.0) u=0.0;
   return pow(10.0,log_p_tab[1]+u*(log_p_tab[2]-log_p_tab[1]));
 }
 return pow(10.0,interp(log_h_tab,log_p_tab,n_tab,log10(hh), n_nearest_pt));
}'''
REPLACEMENT_H = '''double h_at_p(double pp, 
              double log_h_tab[2001], 
              double log_p_tab[2001],
              int    n_tab, 
              int    *n_nearest_pt)
{
 /* J0740 bounded first EOS bin: use same H(logP) law as p_at_h. */
 if (pp>0.0 && pp<=pow(10.0,log_p_tab[2])) {
   double h0=pow(10.0,log_h_tab[1]);
   double h1=pow(10.0,log_h_tab[2]);
   if (!(h1>h0) || !(log_p_tab[2]>log_p_tab[1])) {
     fprintf(stderr,"J0740 boundary H/P not strictly monotone\\n");
     exit(2);
   }
   double u=(log10(pp)-log_p_tab[1])/(log_p_tab[2]-log_p_tab[1]);
   if (u<0.0) u=0.0;
   return h0+u*(h1-h0);
 }
 return pow(10.0,interp(log_p_tab,log_h_tab,n_tab,log10(pp), n_nearest_pt));
}'''


def patch_source(source:str)->str:
    if source.count(START_P)!=1 or source.count(START_H)!=1:
        raise ValueError("Pinned RNS source functions absent/ambiguous; refuse patch")
    changed=source.replace(START_P,REPLACEMENT_P).replace(START_H,REPLACEMENT_H)
    if changed.count("J0740 bounded first EOS bin")!=2:
        raise ValueError("Source patch incomplete")
    return changed


def bounded_h_from_p(rows:np.ndarray,p:float)->float:
    """H(logP) as in source JESTER log-pressure resampling for first bin."""
    a=np.asarray(rows,float)
    if a.ndim!=2 or a.shape[1]!=4 or len(a)<30 or np.any(a<=0) or not all(np.all(np.diff(a[:,j])>0) for j in (1,2)):
        raise ValueError("Invalid EOS table")
    if not a[0,1] <=p<= a[1,1]:
        raise ValueError("Outside strictly bounded first pressure bin")
    u=math.log(p/a[0,1])/math.log(a[1,1]/a[0,1])
    return float(a[0,2]+u*(a[1,2]-a[0,2]))


def bounded_p_from_h(rows:np.ndarray,h:float)->float:
    a=np.asarray(rows,float)
    if a.ndim!=2 or a.shape[1]!=4 or len(a)<30 or not math.isfinite(h) or not a[0,2]<=h<=a[1,2]:
        raise ValueError("Outside strictly bounded first enthalpy bin")
    u=(h-a[0,2])/(a[1,2]-a[0,2])
    return float(math.exp(math.log(a[0,1])+u*(math.log(a[1,1])-math.log(a[0,1]))))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('equil_c',type=Path)
    p.add_argument('--manifest',type=Path,required=True)
    a=p.parse_args()
    data=a.equil_c.read_text()
    old_hash=hashlib.sha256(a.equil_c.read_bytes()).hexdigest()
    changed=patch_source(data)
    a.equil_c.write_text(changed)
    new_hash=hashlib.sha256(a.equil_c.read_bytes()).hexdigest()
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    import json
    a.manifest.write_text(json.dumps({"schema":"j0740-RNS-C-first-logh-bin-guard-v1",
         "source_pre_patch_sha256":old_hash,"source_post_patch_sha256":new_hash,
         "patched_source":str(a.equil_c),"method":"H linear vs logP only in the first table bin",
         "safety":"Not native zero-pressure EOS, causality or X-PSI Bayes proof"},indent=2)+"\n")
    print('PATCHED_RNS_EQUIL_C',old_hash,'->',new_hash)

if __name__=='__main__':main()
