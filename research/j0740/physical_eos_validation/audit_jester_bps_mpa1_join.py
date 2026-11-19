#!/usr/bin/env python3
"""Audit a physical BPS-crust to F67 MPA1 core join without changing either input.

The BPS table is from pinned JESTER commit e6768650ce992abfd1153a6833857572fe5cd230.
Its (n,p,e) units are fm^-3 and MeV fm^-3. The F67 table is exploratory and
uses geometric pressure/energy plus dimensionless n/n0; its absolute n is
reconstructed from the stated surface chemical potential and first law.
"""
from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
BPS = HERE / "JESTER_BPS_crust_e6768650.csv"
ORIGINAL_BPS_SHA = "372ce088e061997f7c05594e61e7c624a112d7ce66443c28c4633d03b7da6137"
CORE = HERE / "F67_MPA1_PCHIP_COLD_relative_thermo_20261119.dat"
MODULE = HERE / "mpa1_jester_hybrid_crust_tov.py"
G, C = 6.67430e-11, 299792458.0
MEV_FM3_TO_GEOM = 1.602176634e32 * G / C**4

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run() -> dict:
    spec = importlib.util.spec_from_file_location("mpa1", MODULE)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    eos = mod.EOS(CORE)
    table = np.loadtxt(BPS, delimiter=",", skiprows=1, dtype=float)
    n, p, e = table.T
    if len(n) != 130 or not (np.all(np.diff(n)>0) and np.all(np.diff(p)>0)
                              and np.all(np.diff(e)>0)):
        raise AssertionError("BPS source table shape/monotonicity failed")
    # Compare at the BPS upper endpoint pressure.
    p_bps_geom = float(p[-1] * MEV_FM3_TO_GEOM)
    x = float(np.log(p_bps_geom))
    e_core = float(np.exp(eos.spline(x)))
    h_core = eos.enthalpy_at_logp(x)
    n_core_fm3 = float((e_core+p_bps_geom)/(eos.mu0_geom*np.exp(h_core))/1e45)
    e_bps_geom = float(e[-1]*MEV_FM3_TO_GEOM)
    mu_core_mev = float(mod.MU0_MEV*np.exp(h_core))
    mu_bps_mev = float((e[-1]+p[-1])/n[-1])
    # Also compare e and P at the same baryon density, interpolating only within BPS.
    n_at_p = n_core_fm3
    e_bps_at_n = float(np.interp(n_at_p,n,e))
    p_bps_at_n = float(np.interp(n_at_p,n,p))
    p_core_mev = float(p_bps_geom/MEV_FM3_TO_GEOM)
    e_rel = e_core/e_bps_geom-1
    p_equal_n_rel = p_core_mev/p_bps_at_n-1
    report = {
      "schema":"J0740_BPS_MPA1_JOIN_AUDIT_V1",
      "status":"PASS_AUDIT_FAILS_DIRECT_MATCH",
      "source":{"jester_repo":"nuclear-multimessenger-astronomy/jester",
        "jester_commit":"e6768650ce992abfd1153a6833857572fe5cd230",
        "bps_original_npz_sha256":ORIGINAL_BPS_SHA,"bps_csv_sha256":sha(BPS),
        "bps_rows":len(n),"bps_units":"n: fm^-3; p,e: MeV fm^-3",
        "core_table_sha256":sha(CORE),"core_rows":2425,"source_core_is_exploratory":True},
      "at_bps_upper_pressure":{"n_bps_fm3":float(n[-1]),"p_bps_mev_fm3":float(p[-1]),
        "e_bps_mev_fm3":float(e[-1]),"p_geom_m-2":p_bps_geom,
        "e_core_mev_fm3_equivalent":e_core/MEV_FM3_TO_GEOM,
        "relative_energy_mismatch_core_over_bps":e_rel,
        "n_core_fm3_firstlaw_mu_surface_930p4":n_core_fm3,
        "mu_core_mev":mu_core_mev,"mu_bps_mev":mu_bps_mev,
        "relative_mu_mismatch":mu_core_mev/mu_bps_mev-1},
      "at_equal_baryon_density":{"n_fm3":n_at_p,
        "e_bps_mev_fm3":e_bps_at_n,"p_bps_mev_fm3":p_bps_at_n,
        "e_core_mev_fm3":e_core/MEV_FM3_TO_GEOM,
        "p_core_mev_fm3":p_core_mev,
        "relative_pressure_mismatch_core_over_bps":p_equal_n_rel},
      "interpretation":"The authentic BPS table is not directly thermodynamically matched to the F67 exploratory MPA1-PCHIP core at its upper endpoint. The prior power-law crust is not upgraded to BPS by this result. A new explicitly named interpolating EOS and full TOV/RNS/inference validation would be required.",
      "physical_eos_acceptance":"NOT_ESTABLISHED",
      "new_bps_joined_tov":"NOT_RUN",
      "new_bps_joined_rns":"NOT_RUN",
      "source_native_xpsi_marginalization":"NOT_RUN",
      "final_eos_bayes":"NOT_RUN"
    }
    if not abs(e_rel-(-0.04446460823524645))<2e-8: raise AssertionError("same-pressure energy mismatch changed")
    if not abs(p_equal_n_rel-0.07593139553746786)<2e-8:
        raise AssertionError("same-density pressure mismatch changed")
    return report

if __name__ == "__main__":
    result=run()
    out=HERE/"JESTER_BPS_MPA1_join_audit_20261119.json"
    out.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2,sort_keys=True))

