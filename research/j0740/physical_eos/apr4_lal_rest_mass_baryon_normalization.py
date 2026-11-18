#!/usr/bin/env python3
"""Derive APR4_EPP baryon number density under LALSuite's rest-mass convention.

For cold matter h(0)=0 and rho_b=(e+p) exp(-h) in geometrized units.
Set n_b=rho_b/m_u, with m_u=1.66053906660e-27 kg. This is an explicit
baryonic-mass convention; it does not claim an independently measured
microphysical surface chemical potential for the approximate APR4_EPP crust.
"""
from __future__ import annotations
import csv, hashlib, json, math
from pathlib import Path

HERE = Path(__file__).resolve().parent
INPUT = HERE / "APR4_EPP_firstlaw_n_shape.csv"
MANIFEST = HERE / "SHA256_manifest.json"
EXPECTED_INPUT_SHA256 = "ce442eeef79753872a268e67ae5a98a7db80d5d2d5864a4e87a0c2e6c974dfd1"
EXPECTED_EOS_SHA256 = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
EXPECTED_NATIVE_TABLE_SHA256 = "2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f"
M_U_KG = 1.66053906660e-27
G_SI = 6.67430e-11
C_SI = 299792458.0
M_U_GEOM_M = G_SI * M_U_KG / C_SI**2


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def calculate() -> dict:
    digest = sha256(INPUT)
    if digest != EXPECTED_INPUT_SHA256:
        raise ValueError(f"input SHA mismatch: {digest}")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    declared = {item["file"]: item["sha256"] for item in manifest["artifacts"]}
    if declared.get("JESTER_pinned_APR4_EPP.npz") != EXPECTED_EOS_SHA256:
        raise ValueError("original JESTER EOS provenance mismatch")
    if declared.get("LALSimNeutronStarEOS_APR4_EPP_native_7.26.4.dat") != EXPECTED_NATIVE_TABLE_SHA256:
        raise ValueError("native LAL table provenance mismatch")
    with INPUT.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 865:
        raise ValueError(f"expected 865 source samples, got {len(rows)}")
    n_values = []
    ratios = []
    for row in rows:
        e = float(row["e_geom_m-2"])
        p = float(row["p_geom_m-2"])
        h = float(row["h"])
        firstlaw_n_times_mu0 = float(row["firstlaw_n_times_mu0_m-2"])
        source_n = float(row["n_source_approx_m-3"])
        n_geom = firstlaw_n_times_mu0 / M_U_GEOM_M
        expected = (e + p) * math.exp(-h) / M_U_GEOM_M
        if not math.isclose(n_geom, expected, rel_tol=2e-14, abs_tol=0.0):
            raise ValueError("first-law baryon density identity failed")
        if not (math.isfinite(n_geom) and n_geom > 0 and math.isfinite(source_n) and source_n > 0):
            raise ValueError("nonpositive/nonfinite baryon density")
        n_values.append(n_geom)
        ratios.append(n_geom / source_n)
    if any(b <= a for a, b in zip(n_values, n_values[1:])):
        raise ValueError("baryon density is not strictly increasing")
    return {
        "schema": "J0740_APR4_LAL_REST_MASS_BARYON_NORMALIZATION_v1",
        "status": "LAL_STANDARD_BARYON_MASS_NORMALIZATION_ESTABLISHED; MICROPHYSICAL_SURFACE_MU0_NOT_INDEPENDENTLY_MEASURED",
        "source_npz_sha256": EXPECTED_EOS_SHA256,
        "native_lalsuite_table_sha256": EXPECTED_NATIVE_TABLE_SHA256,
        "firstlaw_shape_csv_sha256": digest,
        "source_rows": len(rows),
        "normalization": {
            "convention": "LALSuite rest-mass density rho_b=(e+p)*exp(-h), n_b=rho_b/m_u",
            "baryon_mass_unit_kg": M_U_KG,
            "baryon_mass_unit_geometric_m": M_U_GEOM_M,
            "surface_condition": "h(P=0)=0; low-pressure continuation is the recorded Gamma=5/3 branch",
            "interpretation": "absolute n_b is fixed under the explicitly stated m_u convention; this is not an independent microscopic determination of the APR4_EPP crust surface chemical potential"
        },
        "n_b_fm-3": {"first_export_sample": n_values[0] / 1e45, "last_export_sample": n_values[-1] / 1e45},
        "ratio_to_jester_e_over_mavg_proxy": {"first_export_sample": ratios[0], "last_export_sample": ratios[-1]},
        "native_crust_nodes": 1447,
        "native_crust_min_pressure_geom_m-2": 1.9389363172276004e-31,
        "original_source_modified": False,
        "full_photon_xpsi_and_final_eos_bayes": "NOT_RUN"
    }


if __name__ == "__main__":
    result = calculate()
    out = HERE / "APR4_LAL_rest_mass_baryon_normalization_20261118.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    result["result_json_sha256"] = sha256(out)
    print(json.dumps(result, indent=2, sort_keys=True))
