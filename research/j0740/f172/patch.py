import sys
from pathlib import Path
p=Path(sys.argv[1])/'equil.c';s=p.read_text()
a='d_gama_ss=s1*deriv_s(dgds,s,m)+(1.0-2.0*sgp)';b='d_gama_ss=s1*((s>1 && s<SDIV)?(gama[s+1][m]-2.0*gama[s][m]+gama[s-1][m])/SQ(DS):deriv_s(dgds,s,m))+(1.0-2.0*sgp)'
c='d_gama_mm=m1*deriv_m(dgdm,s,m)-2.0*mum*d_gama_m;';d='d_gama_mm=m1*((m>1 && m<MDIV)?(gama[s][m+1]-2.0*gama[s][m]+gama[s][m-1])/SQ(DM):deriv_m(dgdm,s,m))-2.0*mum*d_gama_m;'
assert s.count(a)==s.count(c)==1
p.write_text(s.replace(a,b).replace(c,d))
print('F172_ALPHA_DIRECT_SECOND_DERIVATIVE_PATCH')
