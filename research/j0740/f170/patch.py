import sys
from pathlib import Path
p=Path(sys.argv[1])/'equil.c';s=p.read_text()
anchor='#include "exact_barotrope.h"';assert s.count(anchor)==1
s=s.replace(anchor,anchor+'\n#include "split_quad.h"')
a=s.index('      /* RADIAL INTEGRATION */');b=s.index('      free_dmatrix(D1_rho',a)
old=s[a:b];assert old.count('D2_rho[s][n+1]=sum_rho;')==2 and 'k+2<=s' in old
new=r'''
      /* Split Green kernel at s, not across its derivative kink. */
      D2_rho = dmatrix(1,SDIV,1,LMAX+1);
      D2_gama = dmatrix(1,SDIV,1,LMAX+1);
      D2_omega = dmatrix(1,SDIV,1,LMAX+1);
      for(s=1;s<=SDIV;s++){
        double vr[SDIV+1],vg[SDIV+1],vo[SDIV+1];
        for(n=0;n<=LMAX;n++){
          for(k=1;k<=SDIV;k++){
            vr[k]=f_rho[s][n+1][k]*D1_rho[n+1][k];
            if(n>0){
              vg[k]=f_gama[s][n+1][k]*D1_gama[n+1][k];
              vo[k]=(k<s?f_rho[s][n+1][k]:f_gama[s][n+1][k])*D1_omega[n+1][k];
            }
          }
          D2_rho[s][n+1]=jq_split(vr,SDIV,s,DS);
          D2_gama[s][n+1]=n?jq_split(vg,SDIV,s,DS):0.;
          D2_omega[s][n+1]=n?jq_split(vo,SDIV,s,DS):0.;
        }
      }
'''
p.write_text(s[:a]+new+s[b:]);(p.parent/'split_quad.h').write_bytes((Path(__file__).parent/'split_quad.h').read_bytes())
print('F170_RADIAL_QUADRATURE_PATCH_APPLIED')
