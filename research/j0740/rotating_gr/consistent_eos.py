"""Explicit new barotrope: raw-knot Steffen E(P), integrated h, gas surface."""
from pathlib import Path
import math,numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
from numpy.polynomial.legendre import leggauss
from steffen_interpolant import monotone_steffen
G=6.67430e-11;C=299792458.;MSUN=1.988409870698051e30;MB=1.66053906660e-27
class ConsistentEOS:
 def __init__(self,raw,subdivisions=16):
  self.raw=np.asarray(raw);self.x=np.log(raw[:,0]);self.y=np.log(raw[:,1]);self.spline=monotone_steffen(self.x,self.y)
  self.p0,self.e0=raw[0,:2];self.h0=2.5*math.log1p(self.p0/self.e0)
  grid=np.concatenate([np.linspace(a,b,subdivisions+1)[:-1] for a,b in zip(self.x[:-1],self.x[1:])]+[self.x[-1:]])
  g,w=leggauss(12);a=grid[:-1];b=grid[1:];t=(a+b)[:,None]/2+(b-a)[:,None]*g/2
  integrand=np.exp(t)/(np.exp(self.spline(t))+np.exp(t))
  h=self.h0+np.r_[0.,np.cumsum((b-a)/2*(integrand@w))]
  assert np.all(np.diff(h)>0)
  self.grid=grid;self.hgrid=h;self.h_of_x=PchipInterpolator(grid,h);self.x_of_h=PchipInterpolator(h,grid)
 def energy(self,p):
  p=np.asarray(p);return np.where(p<self.p0,self.e0*(p/self.p0)**.6,np.exp(self.spline(np.log(np.maximum(p,self.p0)))))
 def h(self,p):
  if p<self.p0:return 2.5*math.log1p((self.p0/self.e0)*(p/self.p0)**.4)
  return float(self.h_of_x(math.log(p)))
 def pressure(self,h):
  if h<=0:return 0.
  if h<self.h0:return self.p0*(math.expm1(h/2.5)/(self.p0/self.e0))**2.5
  return math.exp(float(self.x_of_h(h)))
 def at_h(self,h):
  p=self.pressure(h);return p*1e6,float(self.energy(p))*1e6 if p>0 else 0.
 def cs2(self,p):
  if p<self.p0:return (5/3)*p/float(self.energy(p))
  xp=math.log(p);return math.exp(xp-float(self.spline(xp)))/float(self.spline(xp,1))
 def extrema(self,pc=None):
  limit=self.x[-1] if pc is None else math.log(pc);values=[((5/3)*self.p0/self.e0,self.x[0])]
  for i in range(len(self.x)-1):
   hi=min(self.x[i+1],limit)-self.x[i]
   if hi<=0:break
   a,b,c,d=self.spline.c[:,i];D=np.array([c,2*b,3*a]);square=np.polynomial.polynomial.polymul(D,D)
   equation=-np.pad(square,(0,max(0,5-len(square))));equation[:3]+=D;equation[:2]-=[2*b,6*a]
   trimmed=np.trim_zeros(equation,'b');points=[0.,hi]
   if len(trimmed)>1:
    points += [float(r.real) for r in np.polynomial.polynomial.polyroots(trimmed) if abs(r.imag)<1e-8 and 0<r.real<hi]
   for t in points:values.append((self.cs2(math.exp(self.x[i]+t)),self.x[i]+t))
  return sorted(values,key=lambda v:v[1])
 def causal_pressure_limit(self):
  vals=self.extrema();last=vals[0]
  for now in vals[1:]:
   if now[0]>=1:
    root=brentq(lambda x:self.cs2(math.exp(x))-1,last[1],now[1],xtol=1e-12);return math.exp(root),False
   last=now
  return float(self.raw[-1,0]),True
 def rns_rows(self,subdivisions=8,gas_depth=10):
  xs=np.unique(np.r_[np.linspace(self.x[0]-gas_depth*math.log(10),self.x[0],48),
      *[np.linspace(a,b,subdivisions+1) for a,b in zip(self.x[:-1],self.x[1:])]])
  p=np.exp(xs);e=self.energy(p);h=np.array([self.h(v) for v in p]);n=(e+p)*np.exp(-h)*C*C/(G*MB)/1e6
  rows=np.column_stack([e*C*C/G*1e-3,p*C**4/G*10,h*(C*100)**2,n])
  assert len(rows)<=2000 and all(np.all(np.diff(rows[:,j])>0) for j in range(4))
  return rows
