#!/usr/bin/env python3
"""Audit JESTER's APR4_EPP baryon-density export against cold first law.

Input NPZ is read-only. The first-law shape is reconstructed from the supplied
pseudo-enthalpy h. Its absolute normalization remains parameterized by the
surface baryon chemical potential mu0, which this NPZ does not supply.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np

SOURCE = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\User\AppData\Local\SentinelX\uploads\j0740_20261117_sources\APR4_EPP.npz"
)
OUT = Path(__file__).resolve().parent
EXPECTED_SHA256 = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
M_N_MEV = 939.5654205203889
M_P_MEV = 938.2720881604904
MEV_J = 1.602176634e-13
C = 299792458.0
G = 6.67430e-11


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


assert SOURCE.is_file(), f"missing source: {SOURCE}"
source_sha = sha256(SOURCE)
assert source_sha == EXPECTED_SHA256, f"wrong source SHA256: {source_sha}"

with np.load(SOURCE, allow_pickle=False) as z:
    p, e, n, h, cs2, dlog = (z[k].astype(np.float64) for k in ("p", "e", "n", "h", "cs2", "dloge_dlogp"))
    assert str(z["eos_name"]) == "APR4_EPP"
    assert str(z["source"]) == "LALSimulation"

assert all(a.shape == (865,) for a in (p, e, n, h, cs2, dlog))
assert np.all(np.isfinite(np.stack((p, e, n, h, cs2, dlog))))
assert np.all(np.diff(p) > 0) and np.all(np.diff(e) > 0)
assert np.all((cs2 > 0) & np.isfinite(cs2))

m_avg = 0.5 * (M_N_MEV + M_P_MEV) * MEV_J / C**2 * G / C**2
n_approx = e / m_avg
proxy_rel_error = float(np.max(np.abs(n / n_approx - 1.0)))
assert proxy_rel_error < 2e-14, f"NPZ n is not e/m_avg: {proxy_rel_error}"

# For cold matter, h = integral dP/(e+P), and first law gives
# mu=(e+P)/n = mu0*exp(h), hence n = (e+P)*exp(-h)/mu0.
# This reconstructed numerator is exact up to native table interpolation.
mu_proxy = (e + p) / n
log_mu_residual = np.log(mu_proxy / mu_proxy[0]) - (h - h[0])
shape_over_nproxy = (e + p) * np.exp(-h) / (m_avg * n)
first_acausal = int(np.flatnonzero(cs2 > 1.0)[0])
peak_cs2 = int(np.argmax(cs2))
assert float(np.max(np.abs(log_mu_residual))) > 0.5
assert first_acausal == 812
assert abs(float(cs2[first_acausal]) - 1.0290674703621383) < 1e-12
assert abs(float(cs2[peak_cs2]) - 1.0982782452928908) < 1e-12

rows = OUT / "APR4_EPP_firstlaw_n_shape.csv"
with rows.open("w", encoding="utf-8", newline="") as f:
    f.write("index,p_geom_m-2,e_geom_m-2,h,cs2,n_source_approx_m-3,firstlaw_n_times_mu0_m-2,firstlaw_n_over_n_source_if_mu0_mavg\n")
    for i in range(len(p)):
        f.write(f"{i},{p[i]:.17g},{e[i]:.17g},{h[i]:.17g},{cs2[i]:.17g},{n[i]:.17g},{(e[i]+p[i])*np.exp(-h[i]):.17g},{shape_over_nproxy[i]:.17g}\n")

result = {
    "status": "FIRST_LAW_SHAPE_RECONSTRUCTED; ABSOLUTE_CRUST_NORMALIZATION_NOT_ESTABLISHED",
    "source_sha256": source_sha,
    "source_rows": len(p),
    "m_avg_geom_m": m_avg,
    "n_source_equals_e_over_m_avg_max_relative_error": proxy_rel_error,
    "mu_proxy_over_enthalpy_first_law_log_residual_max_abs": float(np.max(np.abs(log_mu_residual))),
    "first_law_shape": "n(mu0)=(e+p)*exp(-h)/mu0; mu0 is the physical zero-pressure baryon chemical potential",
    "first_law_shape_times_mu0_units": "m^-2",
    "firstlaw_n_over_source_n_if_mu0_mavg": {
        "first_row": float(shape_over_nproxy[0]),
        "last_row": float(shape_over_nproxy[-1]),
        "min": float(shape_over_nproxy.min()),
        "max": float(shape_over_nproxy.max()),
    },
    "first_acausal_sample_index": first_acausal,
    "first_acausal_p_geom_m-2": float(p[first_acausal]),
    "first_acausal_cs2": float(cs2[first_acausal]),
    "peak_cs2": float(cs2[peak_cs2]),
    "peak_cs2_index": peak_cs2,
    "source_shell_anchor_available_in_npz": False,
    "physical_mu0_value": None,
    "limitation": "The NPZ starts at P=1e26 Pa and contains no low-pressure crust table or surface chemical-potential anchor. n(mu0) supplies shape only; do not relabel a chosen m_avg or neutron mass as validated APR4 crust normalization.",
    "original_source_modified": False,
    "csv_sha256": sha256(rows),
    "script_sha256": sha256(Path(__file__)),
}
out = OUT / "APR4_EPP_firstlaw_n_audit.json"
out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
print("RESULT_SHA256", sha256(out))

