/* Exact piecewise-linear E(P) + analytic low-P continuation. All energies
   in a single consistent unit; H dimensionless. One EOS per process. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
static int jb_n;
static double jb_p[2001],jb_e[2001],jb_h[2001],jb_s[2001];
static void jb_error(const char *m) { fprintf(stderr,"EXACT_EOS_ERROR %s\n",m);exit(93); }
static void jb_init(int n,const double *p,const double *e){
 int i;if(n<2||n>2000)jb_error("node count");jb_n=n;
 for(i=1;i<=n;i++){jb_p[i]=p[i-1];jb_e[i]=e[i-1];if(!(jb_p[i]>0&&jb_e[i]>0))jb_error("nonpositive");}
 if(.75*jb_e[1]/jb_p[1]<1.)jb_error("crust causality");
 jb_h[1]=4.*log1p(jb_p[1]/jb_e[1]);
 for(i=1;i<n;i++){
  double dp=jb_p[i+1]-jb_p[i],de=jb_e[i+1]-jb_e[i];
  if(!(dp>0&&de>0))jb_error("monotonicity");
  jb_s[i]=de/dp;if(jb_s[i]<1.-1e-8)jb_error("causality");
  jb_h[i+1]=jb_h[i]+log1p((de+dp)/(jb_p[i]+jb_e[i]))/(1.+jb_s[i]);
  if(!(jb_h[i+1]>jb_h[i]))jb_error("enthalpy monotonicity");
 }
}
static int jb_loc(const double *x,double v){
 int l=1,r=jb_n,m;
 if(!isfinite(v)||v>x[r]*(1.+1e-12))jb_error("outside upper support");
 while(r-l>1){m=(r+l)/2;if(v<x[m])r=m;else l=m;}return l;
}
static double jb_e_at_p(double p){
 int i;if(p<=0)return 0.;if(p<jb_p[1])return jb_e[1]*pow(p/jb_p[1],.75);
 i=jb_loc(jb_p,p);return jb_e[i]+jb_s[i]*(p-jb_p[i]);
}
static double jb_p_at_e(double e){
 int i;if(e<=0)return 0.;if(e<jb_e[1])return jb_p[1]*pow(e/jb_e[1],4./3.);
 i=jb_loc(jb_e,e);return jb_p[i]+(e-jb_e[i])/jb_s[i];
}
static double jb_h_at_p(double p){
 int i;if(p<=0)return 0.;if(p<jb_p[1])return 4.*log1p((jb_p[1]/jb_e[1])*pow(p/jb_p[1],.25));
 i=jb_loc(jb_p,p);return jb_h[i]+log1p((1.+jb_s[i])*(p-jb_p[i])/(jb_p[i]+jb_e[i]))/(1.+jb_s[i]);
}
static double jb_p_at_h(double h){
 int i;if(h<=0)return 0.;if(h<jb_h[1])return jb_p[1]*pow(expm1(h/4.)/(jb_p[1]/jb_e[1]),4.);
 i=jb_loc(jb_h,h);return jb_p[i]+(jb_p[i]+jb_e[i])*expm1((1.+jb_s[i])*(h-jb_h[i]))/(1.+jb_s[i]);
}
/* n times mu_surface in same energy unit. n normalization is a convention. */
static double jb_nmu_at_e(double e){double p=jb_p_at_e(e);return (e+p)*exp(-jb_h_at_p(p));}
