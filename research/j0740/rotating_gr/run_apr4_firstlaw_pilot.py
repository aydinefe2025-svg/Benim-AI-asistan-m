"""Make and audit two deliberately distinct APR4 candidate RNS tables.

1st three columns are strictly identical; ONLY last baryon density differs.
Still model assumed: polytropic P->0 continuation, cannot claim physical crust.
This runner writes no scientific GR result; C RNS must execute separately.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
from apr4_firstlaw_crust import from_pinned,write_rns,checksum


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source',required=True,type=Path)
    ap.add_argument('--out',required=True,type=Path)
    opt=ap.parse_args()
    opt.out.mkdir(exist_ok=True,parents=True)
    c=from_pinned(opt.source)
    center=c.at_e(c.center_e)
    max_e=1.08*c.center_e
    end=c.at_e(max_e)
    causal=c.causal_screen(end['p'])
    n_ratio=center['n']/center['source_approx_n']
    reports={
        'status':'PASS_PROVISIONAL_C1_LOW_PRESSURE_AND_FIRSTLAW_TABLES_NOT_PHYSICAL_EOS_CERTIFICATION',
        'scientific_type':'assumed log(e)-log(p) PCHIP plus low-P epsilon∝P^beta extension; warm-up / baryon n ablation only',
        'source_sha256':checksum(opt.source),
        'source_rows':len(c.p),
        'source_p0_geom_m2':c.p0,
        'source_e0_geom_m2':c.e0,
        'low_p_extrap_beta':c.beta,
        'mu0_geo_m_per_baryon':c.mu_geom,
        'chemical_mass_kg':c.mu_geom*(299792458.0**2)/6.67430e-11,
        'at_Pmin_h_from_surface':c.h0,
        'at_Pmin_h_native':float(c.source_h[0]),
        'at_Pmin_n_firstlaw_over_source':c.at_p(c.p0)['n']/c.n[0],
        'center_geom_e':c.center_e,
        'center_pressure_geom':center['p'],
        'center_enthalpy_absolute':center['h'],
        'center_source_native_enthalpy':float(np.interp(math.log(center['p']),c.x,c.source_h)),
        'center_n_firstlaw_over_source':n_ratio,
        'max_e_over_center':max_e/c.center_e,
        'candidate_pressure_ceiling_geom':end['p'],
        'tested_candidate_causality':causal,
        'no_claims':['no native-LAL EOS or thermodynamic crust proof','no measured baryonic M0 change without running actual RNS','no valid APR4 EOS beyond chosen central_density 1.08 margin','zero-pressure physical microphysics is an explicit unvalidated continuation assumption'],
        'tables':{}
    }
    for nrows in (196,200):
        true,naive,states=c.make_table(end['p'],points=nrows)
        names={'n_firstlaw':opt.out/f'APR4_firstlaw_P0pilot_{nrows}.rns','n_approx':opt.out/f'APR4_sourceN_approx_P0pilot_{nrows}.rns'}
        write_rns(names['n_firstlaw'],true)
        write_rns(names['n_approx'],naive)
        # no interpolation scheme can change the first three columns in this n-ablation
        one={str(q):checksum(path) for q,path in names.items()}
        reports['tables'][str(nrows)]={'file_sha256':one,'first_three_columns_identical':bool(np.array_equal(true[:,:3],naive[:,:3])),
          'n_source_over_firstlaw_center':float(1/n_ratio),
          'pressure_floor_geom_ratio':float(states[0]['p']/c.p0),
          'energy_floor_gcm3':float(true[0,0]),
          'lowest_h_dimensionless':float(states[0]['h']),
          'max_cs2_grid':float(max(z['cs2'] for z in states)),
          'density_minmax_gcm3':[float(true[:,0].min()),float(true[:,0].max())],
          'max_n_column_diff_fraction':float(np.max(np.abs(true[:,3]/naive[:,3]-1)))}
        assert reports['tables'][str(nrows)]['first_three_columns_identical']
        assert all(np.diff(true[:,i]).min()>0 for i in range(4))
    report=opt.out/'J0740_APR4_FIRSTLAW_POLYTROPIC_P0_PILOT_20261117.json'
    report.write_text(json.dumps(reports,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':reports['status'],'causality':causal,'firstlaw_over_original_n_at_center':n_ratio,
        'p0_h_analytic':c.h0,'p0_h_native':c.source_h[0],'center_enthalpy':center['h'],
        'center_native_enthalpy':reports['center_source_native_enthalpy'],
        'output_json':str(report),'output_sha256':checksum(report),
        'rns_tables':reports['tables']},ensure_ascii=False))

if __name__=='__main__':main()
