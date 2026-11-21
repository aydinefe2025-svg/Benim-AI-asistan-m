"""Audit source-native negative sound-speed-square knots without modifying EOS.

Pinned JESTER/LALSuite source: cs2 = p / (e * dloge_dlogp).  This
checks the identity, adjacent source samples, and the shared low-density
outlier's pressure. A single knot is *not* a physical crust instability proof.
"""
from __future__ import annotations
import argparse, json, hashlib, math
from pathlib import Path
import numpy as np

C,G=299792458.,6.67430e-11
C2G=C*C/G*1e-3
EOS=("APR4_EPP","ENG","MPA1","MS1","MS1B","WFF1","WFF2")
SOURCE_SHA="e6768650ce992abfd1153a6833857572fe5cd230"

def diagnose_arrays(p,e,cs2,dlog,h):
    p,e,cs2,dlog,h=map(lambda z:np.asarray(z,float),(p,e,cs2,dlog,h))
    if (any(z.ndim!=1 or len(z)<30 for z in (p,e,cs2,dlog,h)) or
        len({len(z) for z in (p,e,cs2,dlog,h)})!=1 or
        not all(np.all(np.isfinite(z)) for z in (p,e,cs2,dlog,h)) or
        np.any(p<=0) or np.any(e<=0) or np.any(np.diff(p)<=0)):
        raise ValueError("Invalid JESTER source arrays")
    analyt=p/(e*dlog)
    if not np.allclose(analyt,cs2,rtol=5e-9,atol=5e-12):
        raise ValueError("Source native cs2 is not consistent with analytic dloge_dlogp")
    neg=np.where(cs2<0)[0]
    nodes=[]
    for i in neg:
        k=int(i)
        nbr=[]
        for j in range(max(0,k-2),min(len(p),k+3)):
            left=(p[j]-p[j-1])/(e[j]-e[j-1]) if j>0 and e[j]!=e[j-1] else None
            right=(p[j+1]-p[j])/(e[j+1]-e[j]) if j+1<len(e) and e[j+1]!=e[j] else None
            nbr.append({"index":j,"rho_g_cm3":float(e[j]*C2G),"p_geom_m_minus2":float(p[j]),
                        "cs2_native":float(cs2[j]),"dloge_dlogp":float(dlog[j]),
                        "energy_geom_m_minus2":float(e[j]),"h":float(h[j]),
                        "left_secant_dp_de":float(left) if left is not None else None,
                        "right_secant_dp_de":float(right) if right is not None else None})
        nodes.append({"index":k,"rho_g_cm3":float(e[k]*C2G),"p_geom_m_minus2":float(p[k]),
                      "cs2_native":float(cs2[k]),"dloge_dlogp":float(dlog[k]),
                      "neighborhood":nbr})
    return {"source_rows":int(len(p)),"negative_native_cs2_count":int(len(neg)),
            "negative_native_cs2_nodes":nodes,"e_nonincreasing_edges":int(np.count_nonzero(np.diff(e)<=0)),
            "source_analytic_identity_verified":True,
            "cs2_min":float(cs2.min()),"cs2_max":float(cs2.max()),
            "min_pressure_geom":float(p[0]),"max_pressure_geom":float(p[-1])}

def audit(source):
    out={}
    for name in EOS:
        file=source/(name+".npz")
        with np.load(file,allow_pickle=False) as z:
            x=diagnose_arrays(z['p'],z['e'],z['cs2'],z['dloge_dlogp'],z['h'])
        x["source_sha256"]=hashlib.sha256(file.read_bytes()).hexdigest()
        out[name]=x
    negs=[(k,v['negative_native_cs2_nodes'][0]['p_geom_m_minus2']) for k,v in out.items()
          if v['negative_native_cs2_nodes']]
    if negs:
        ps=np.array([q for k,q in negs]); pressure_relative_spread=float((ps.max()-ps.min())/ps.mean())
    else:pressure_relative_spread=None
    return {"schema":"j0740-seven-source-native-crust-negative-cs2-audit-v1",
            "jester_upstream_commit":SOURCE_SHA,
            "source_generator":"jesterTOV/tabulated_eos/generate_lalsuite_eos.py",
            "generator_identity":"cs2=p/(e*dloge_dlogp); derivative queried from LALSimulation analytic EOS routine",
            "negative_node_same_pressure_relative_spread":pressure_relative_spread,
            "negative_node_count_eos":len(negs),
            "caveat":"Matching low-pressure negative-derivative source knots alone do not prove the cause, shared crust prescription or physical instability. No smoothing or clipping performed.",
            "eos":out}

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--source-dir",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path);a=parser.parse_args()
    result=audit(a.source_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n")
    for k,v in result['eos'].items():
        neg=v['negative_native_cs2_nodes']
        print(k,'negative_nodes',v['negative_native_cs2_count'],
              'rho',neg[0]['rho_g_cm3'] if neg else None,
              'pressure',neg[0]['p_geom_m_minus2'] if neg else None,flush=True)
    print('common negative-source pressure relative spread',result['negative_node_same_pressure_relative_spread'])

if __name__=='__main__':main()
