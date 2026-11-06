"""Literal pure-NumPy transcription of X-PSI v1.2.1 Cython gravity kernel.

Public reference: xpsi-group/xpsi, tag v1.2.1,
  xpsi/surface_radiation_field/effective_gravity_universal.pyx
Git blob SHA 8774124fbd962aa0e420e0cd72cbe7f1f0330574.
Not the compiled X-PSI function; numerically equivalent algebra checked by tests.
"""
import numpy as np
C_XPSI=2.99792458e8
RG1_XPSI_KM=1.47662512

def xpsi_v121_log10_g(m_msun, r_eq_km, cos_theta, spin_hz=346.53637):
    m=np.asarray(m_msun,float)
    r=np.asarray(r_eq_km,float)
    mu=np.asarray(cos_theta,float)
    m,r,mu=np.broadcast_arrays(m,r,mu)
    if np.any(~np.isfinite(m+r+mu)) or np.any(m<=0) or np.any(r<=0) or np.any(np.abs(mu)>1):
        raise ValueError('Invalid mass, radius or colatitude')
    x=RG1_XPSI_KM*m/r
    if np.any(x>=.5):raise ValueError('Outside Schwarzschild r>2rg')
    eps=(2*np.pi*spin_hz)**2*(r*1000)**3/(RG1_XPSI_KM*1000*m*C_XPSI**2)
    esq=eps
    esqsq=eps*eps
    g0=x*C_XPSI**2/(r*1000*np.sqrt(1-2*x))
    ce=-.791+.776*x
    cp=1.138-1.431*x
    de=(-1.315+2.431*x)*esq*x
    dp=(.653-2.864*x)*esq*x
    d60=(13.47-27.13*x)*esq*x
    fe=-1.172*x*esqsq
    fp=.975*x*esqsq
    factor=1+(ce+de+fe)*esq*(1-mu*mu)
    factor=factor+(cp+dp+fp-d60)*esq*mu*mu+d60*esq*np.abs(mu)
    if np.any(factor<=0):raise ValueError('Negative effective gravity')
    return np.log10(factor*g0)+2

def native_pole_equator_gravity(m,r,spin_hz=346.53637):
    m,r=np.broadcast_arrays(np.asarray(m,float),np.asarray(r,float))
    return xpsi_v121_log10_g(m,r,1,spin_hz),xpsi_v121_log10_g(m,r,0,spin_hz)
