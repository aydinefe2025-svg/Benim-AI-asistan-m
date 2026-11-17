"""Independent, read-only comparison of APR4_EPP NPZ with LALSuite's documented SLy crust."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

SOURCE_SHA256 = "639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88"
G = 6.67430e-11
C = 299792458.0
LAL_RHO_SI = np.array([0.0, 2.44033979e10, 3.78358138e14, 2.62780487e15])
LAL_K_SI = np.array(
    [1.0801158752700761e7, 1.311359898998385e10,
     6.507604807550857e19, 3.053461077133694e8]
)
LAL_GAMMA = np.array([1.58424999, 1.28732904, 0.62223344, 1.35692395])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _relative_max(x: np.ndarray, y: np.ndarray, mask: np.ndarray) -> dict:
    d = np.abs(x[mask] / y[mask] - 1.0)
    rows = np.flatnonzero(mask)
    j = int(np.argmax(d))
    i = int(rows[j])
    return {
        "max_abs_relative_error": float(d[j]),
        "source_row": i,
        "source_pressure_geom_m_inv2": float(_ACTIVE_P[i]),
    }


_ACTIVE_P = np.empty(0)


def analyze(source: Path) -> dict:
    global _ACTIVE_P
    if sha256(source) != SOURCE_SHA256:
        raise ValueError("APR4_EPP source SHA-256 differs from the pinned evidence input")
    with np.load(source, allow_pickle=False) as z:
        if z["eos_name"].item() != "APR4_EPP" or z["source"].item() != "LALSimulation":
            raise ValueError("unexpected EOS identity in NPZ")
        p, e, n, h, cs2 = (np.asarray(z[k], dtype=float) for k in ("p", "e", "n", "h", "cs2"))
        rows = len(p)
        if not all(a.shape == p.shape and np.isfinite(a).all() for a in (e, n, h, cs2)):
            raise ValueError("non-finite or mismatched EOS arrays")
        if any(np.any(np.diff(a) <= 0) for a in (p, e, n, h)):
            raise ValueError("source monotonicity failed; values are retained")

        rho_g = G * LAL_RHO_SI / C**2
        k_g = LAL_K_SI * G ** (1.0 - LAL_GAMMA) * C ** (2.0 * LAL_GAMMA - 4.0)
        poly_n = 1.0 / (LAL_GAMMA - 1.0)
        a = np.zeros(4)
        p_breaks = k_g[1:] * rho_g[1:] ** LAL_GAMMA[1:]
        for i in range(1, 4):
            a[i] = a[i - 1] + (poly_n[i - 1] - poly_n[i]) * p_breaks[i - 1] / rho_g[i]

        _ACTIVE_P = p
        piece = np.maximum(0, np.searchsorted(np.r_[0.0, p_breaks], p, side="left") - 1)
        rho = (p / k_g[piece]) ** (1.0 / LAL_GAMMA[piece])
        e_ref = (1.0 + a[piece]) * rho + poly_n[piece] * p
        h_ref = np.log(1.0 + a[piece] + (poly_n[piece] + 1.0) * p / rho)
        cs2_ref = LAL_GAMMA[piece] * p / (e_ref + p)
        mu0_geom = float(np.median(e / n))
        n_ref = rho / mu0_geom
        mask = p <= p_breaks[-1]
        interior = mask.copy()
        for boundary in p_breaks:
            interior &= np.abs(np.log(p / boundary)) > 2e-3
        if not (np.all(np.isfinite(e_ref)) and np.all(np.isfinite(h_ref)) and np.all(np.isfinite(cs2_ref))):
            raise ValueError("reference calculation produced non-finite values")

        n_firstlaw = (e + p) * np.exp(-h) / mu0_geom
        firstlaw_ratio = n / n_firstlaw
        source_mu0_mev = mu0_geom * C**2 / G / 1.7826619216279e-30
        j = 262
        result = {
            "schema": "j0740-apr4-native-lalsuite-crust-comparison-v1",
            "status": "PARTIAL_REFERENCE_MATCH; N_BARYON_AND_TRANSITION_NOT_VALIDATED; EOS_BAYES_NOT_RUN",
            "source": {
                "name": "APR4_EPP", "bytes": source.stat().st_size, "sha256": SOURCE_SHA256,
                "rows": rows, "generator_commit": "e6768650ce992abfd1153a6833857572fe5cd230",
                "generator_lalsuite_dependency": "unpinned in JESTER commit metadata",
            },
            "reference": {
                "implementation": "LALSimNeutronStarEOSPiecewisePolytrope.c low-density SLY4 constants",
                "url": "https://adam-mercer.docs.ligo.org/lalsuite/lalsimulation/_l_a_l_sim_neutron_star_e_o_s_piecewise_polytrope_8c_source.html",
                "paper_url": "https://harvest.aps.org/v2/journals/articles/10.1103/PhysRevD.79.124032/fulltext",
                "version": "published source snapshot; generator build/version is not identified",
                "rho_start_kg_m3": LAL_RHO_SI.tolist(), "K_si": LAL_K_SI.tolist(),
                "gamma": LAL_GAMMA.tolist(),
            },
            "method": {
                "implementation": "independent NumPy transcription; geometric conversion; LAL a_i continuity; e(P), h(P), rho(P), cs2(P)",
                "source_rows_below_last_crust_boundary": int(mask.sum()),
                "source_pressure_range_geom_m_inv2": [float(p[mask][0]), float(p[mask][-1])],
                "reference_boundary_pressures_geom_m_inv2": p_breaks.tolist(),
                "source_mu0_mev": source_mu0_mev,
                "source_unchanged": True,
            },
            "results": {
                "energy_density": _relative_max(e, e_ref, mask),
                "enthalpy": _relative_max(h, h_ref, mask),
                "sound_speed_squared_away_from_piece_boundaries": _relative_max(cs2, cs2_ref, interior),
                "baryon_density_using_source_mu0": _relative_max(n * mu0_geom, rho, mask),
                "source_n_over_enthalpy_firstlaw_n_at_last_row": float(firstlaw_ratio[-1]),
                "source_n_firstlaw_shape_status": "FAIL_SOURCE_N_COLUMN_NOT_FIRST_LAW_SHAPE",
                "second_boundary_adjacent_source_row": {
                    "row": j, "pressure_geom_m_inv2": float(p[j]),
                    "source_cs2": float(cs2[j]), "reference_cs2": float(cs2_ref[j]),
                    "relative_difference": float(abs(cs2[j] / cs2_ref[j] - 1.0)),
                    "source_energy_density_relative_difference": float(e[j] / e_ref[j] - 1.0),
                    "source_enthalpy_relative_difference": float(h[j] / h_ref[j] - 1.0),
                    "retained_without_clamping": True,
                },
            },
            "checks": {
                "source_sha256": sha256(source) == SOURCE_SHA256,
                "source_arrays_finite_and_monotone": True,
                "four_piece_reference_constants_finite": bool(np.isfinite(k_g).all() and np.all(k_g > 0)),
                "reference_thermodynamic_quantities_finite": True,
                "exact_native_generator_identity_proven": False,
            },
            "limits": [
                "The JESTER lalsuite dependency is unpinned; reference comparison is not a bit-for-bit native library validation.",
                "The NPZ begins at positive pressure; source P=0 enthalpy and absolute baryon normalization are not independently available.",
                "The source n column fails first-law shape at high density; no values were clamped or dropped.",
                "A single sampled cs2 near the second crust transition differs by 36.34%; the discrepancy remains unresolved.",
                "No independent TOV-Love solve or unrounded target rotating mass-frequency root was run; EOS_Bayes remains NOT_RUN.",
            ],
            "eos_bayes": "NOT_RUN",
        }
        return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = analyze(args.source)
    args.output.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": data["status"], "output": str(args.output), "bytes": args.output.stat().st_size,
                      "sha256": sha256(args.output), "results": data["results"]}, indent=2))


if __name__ == "__main__":
    main()

