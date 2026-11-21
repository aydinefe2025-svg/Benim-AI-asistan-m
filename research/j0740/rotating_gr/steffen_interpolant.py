"""Steffen monotone Hermite slopes, matching the cached GSL 2.8 formula.

Diagnostic EOS interpolation candidate only. Never edits the pinned tables.
Steffen (1990), A&A 239,443. GSL interpolation/steffen.c (local verified source).
"""
import numpy as np
from scipy.interpolate import CubicHermiteSpline

def monotone_steffen(x,y):
    x=np.asarray(x,float);y=np.asarray(y,float)
    if x.ndim!=1 or x.shape!=y.shape or len(x)<3 or not np.isfinite(x+y).all() or np.any(np.diff(x)<=0) or np.any(np.diff(y)<=0):
        raise ValueError('Strictly increasing finite source knots required; no sorting or repair')
    h=np.diff(x);s=np.diff(y)/h;derivative=np.empty(len(x));derivative[0]=s[0];derivative[-1]=s[-1]
    average=(s[:-1]*h[1:]+s[1:]*h[:-1])/(h[:-1]+h[1:])
    derivative[1:-1]=(np.sign(s[:-1])+np.sign(s[1:]))*np.minimum(np.minimum(abs(s[:-1]),abs(s[1:])),.5*abs(average))
    return CubicHermiteSpline(x,y,derivative,extrapolate=False)

def exact_derivative_bounds(spline):
    """Quadratic derivative extrema on every interval; no dense-grid claim."""
    mins=[];maxs=[]
    for i,h in enumerate(np.diff(spline.x)):
        a,b,c,d=spline.c[:,i];points=[0.,h]
        if a!=0:
            vertex=-b/(3*a)
            if 0<vertex<h:points.append(vertex)
        values=[(3*a*t+2*b)*t+c for t in points];mins.append(min(values));maxs.append(max(values))
    return np.asarray(mins),np.asarray(maxs)
