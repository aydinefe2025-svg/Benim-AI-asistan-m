"""Complementary common-mode low-power screen; fit on normal reference only."""
import numpy as np

def valid(g,p,q):
    return np.isfinite(g)&np.isfinite(p)&np.isfinite(q)&(g>=200)&(g<=1400)&(p>=0)&(q>=0)

def fit(g,p,q):
    b={}
    for lo in range(200,1401,100):
        m=valid(g,p,q)&(g>=lo)&(g<lo+100)&(p>0)&(q>0)
        if m.sum()>=100:
            b[lo]=(float(np.median(p[m]/g[m])),float(np.median(q[m]/g[m])))
    return b

def predict(b,g,p,q):
    result=np.full(len(g),'UNAVAILABLE',dtype='<U13')
    for lo,(a,c) in b.items():
        m=valid(g,p,q)&(g>=lo)&(g<lo+100)
        result[m]='NO_COMMON_LOW'
        result[m&(p<.75*a*g)&(q<.75*c*g)]='COMMON_LOW'
    return result
