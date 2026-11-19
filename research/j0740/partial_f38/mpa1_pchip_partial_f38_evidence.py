#!/usr/bin/env python3
"""Partial F38 evidence contribution for the F68 MPA1-PCHIP RNS curve.

This integrates the published-posterior/source-prior likelihood-ratio surface
over only the four directly solved 196-point-mesh RNS anchors (2.073--2.250
Msun). It deliberately reports a partial, approximate contribution, never a
complete EOS evidence or EOS posterior. Radio mass density is applied once.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import argparse
import zipfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
F38_ZIP = Path(r"C:\Users\User\Documents\Codex\2026-11-17\referenced-chatgpt-conversation-this-is-an-2\outputs\J0740_F48_F47_Reintegral_20261118\F38.zip")
F68_REPORT = Path(r"C:\Users\User\Documents\Codex\2026-11-17\referenced-chatgpt-conversation-this-is-an-2\outputs\J0740_F68_PCHIP_RNS_20261119\F68_DIRECT_RNS_RESULTS_20261119.md")

F68_RUN_ID = 44490729799
MODEL = "MPA1_PCHIP_COLD_V1_EXPLORATORY_NOT_ORIGINAL"
M_ANCHOR = np.array([2.073, 2.175, 2.200, 2.250], dtype=np.float64)
# Direct 196-point-mesh RNS rotating equatorial radii (km), F68 accepted run.
R_ANCHOR_KM = np.array([12.535416706, 12.444887058, 12.417323740, 12.352711910], dtype=np.float64)
M_MU = 2.082
M_SIG = 0.0703
BW = (("0.015_0.20", 0.015, 0.20), ("0.025_0.35", 0.025, 0.35), ("0.040_0.50", 0.040, 0.50))
KINDS = ("weighted", "resampled")
N_GRID = (5001, 10001, 20001, 40001)
EXPECTED_F38_ZIP_SHA256 = "4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307"
EXPECTED_F68_REPORT_SHA256 = "ee7b238c22f28b08a22ae621b1e5a6996f6df07cb4f113acef6d45dc28e1266b"
EXPECTED_SALMI_POSTERIOR_SHA256 = "1549467c64a8801c39213bd28c89737d087cc5ab7a70da1d8d3a32b2d09185c8"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def q_radio(m: np.ndarray) -> np.ndarray:
    z = (m - M_MU) / M_SIG
    norm = math.erf(5 / math.sqrt(2)) - math.erf(-5 / math.sqrt(2))
    # Phi(5)-Phi(-5) = 0.5 * [erf(5/sqrt(2))-erf(-5/sqrt(2))].
    return np.exp(-0.5 * z * z) / (M_SIG * math.sqrt(2 * math.pi) * 0.5 * norm)


def bilinear(m_grid: np.ndarray, r_grid: np.ndarray, values: np.ndarray,
             support: np.ndarray, m: np.ndarray, r: np.ndarray) -> np.ndarray:
    i = np.searchsorted(m_grid, m, side="right") - 1
    j = np.searchsorted(r_grid, r, side="right") - 1
    i = np.clip(i, 0, len(m_grid) - 2)
    j = np.clip(j, 0, len(r_grid) - 2)
    tm = (m - m_grid[i]) / (m_grid[i + 1] - m_grid[i])
    tr = (r - r_grid[j]) / (r_grid[j + 1] - r_grid[j])
    ok = support[i, j] & support[i + 1, j] & support[i, j + 1] & support[i + 1, j + 1]
    if not np.all(ok):
        raise ValueError("curve interpolation touches a hard source-support boundary")
    return ((1-tm)*(1-tr)*values[i,j] + tm*(1-tr)*values[i+1,j]
            + (1-tm)*tr*values[i,j+1] + tm*tr*values[i+1,j+1])


def integrate_surface(zf: zipfile.ZipFile, member: str, n: int) -> dict:
    b = zf.read(member)
    with np.load(io.BytesIO(b), allow_pickle=False) as data:
        mgrid = data["mass_centres"].astype(np.float64)
        rgrid = data["radius_centres_km"].astype(np.float64)
        like = data["relative_likelihood_L_over_Z"].astype(np.float64)
        support = data["hard_source_support"].astype(bool)
    m = np.linspace(M_ANCHOR[0], M_ANCHOR[-1], n)
    r = np.interp(m, M_ANCHOR, R_ANCHOR_KM)
    l = bilinear(mgrid, rgrid, like, support, m, r)
    value = float(np.trapezoid(q_radio(m) * l, m))
    return {"partial_integral": value, "sampled_mass_points": n,
            "curve_mass_range_msun": [float(m[0]), float(m[-1])],
            "curve_radius_range_km": [float(r.min()), float(r.max())],
            "interpolation": "linear between four direct 196-node-mesh RNS anchors; no mass/radius extrapolation",
            "likelihood_surface_member_sha256": hashlib.sha256(b).hexdigest()}


def run(f38_zip: Path = F38_ZIP, f68_report: Path = F68_REPORT) -> dict:
    f38_zip = Path(f38_zip)
    f68_report = Path(f68_report)
    if not f38_zip.is_file() or not f68_report.is_file():
        raise FileNotFoundError("pinned F38/F68 inputs are required")
    f38_sha = sha256(f38_zip)
    f68_sha = sha256(f68_report)
    if f38_sha != EXPECTED_F38_ZIP_SHA256:
        raise ValueError(f"F38 outer SHA mismatch: {f38_sha}")
    if f68_sha != EXPECTED_F68_REPORT_SHA256:
        raise ValueError(f"F68 report SHA mismatch: {f68_sha}")
    with zipfile.ZipFile(f38_zip) as zf:
        bad = zf.testzip()
        if bad is not None:
            raise ValueError(f"F38 ZIP CRC failure: {bad}")
        manifest = json.loads(zf.read("SHA256_manifest.json"))
        checked = {}
        for name, record in manifest.items():
            raw = zf.read(name)
            digest = hashlib.sha256(raw).hexdigest()
            expected = record.get("sha256", record) if isinstance(record, dict) else record
            if digest != expected:
                raise ValueError(f"F38 inner SHA mismatch: {name}")
            checked[name] = {"bytes": len(raw), "sha256": digest}
        source_report = json.loads(zf.read("source_likelihood_report.json"))
        if source_report.get("original_posterior_sha256") != EXPECTED_SALMI_POSTERIOR_SHA256:
            raise ValueError("Salmi published posterior SHA mismatch in F38 report")
        if not source_report.get("source_prior_includes_radio_mass_gaussian"):
            raise ValueError("F38 source prior radio-mass definition is not the expected one")
        if not str(source_report.get("status", "")).startswith("PASS_APPROXIMATE_"):
            raise ValueError("F38 source surface is not an accepted approximate posterior/prior result")
        res = {}
        for kind in KINDS:
            for key, _, _ in BW:
                member = f"posterior_prior_ratio_{kind}_{key}.npz"
                vals = [integrate_surface(zf, member, n) for n in N_GRID]
                fine = vals[-1]["partial_integral"]
                vals[-1]["grid_deltas_to_fine"] = [abs(v["partial_integral"] - fine) for v in vals[:-1]]
                vals[-1]["grid_delta_20001_to_40001"] = abs(vals[-1]["partial_integral"]-vals[-2]["partial_integral"])
                res[f"{kind}_{key}"] = vals[-1]
        weighted_resampled = {}
        for key, _, _ in BW:
            a = res[f"weighted_{key}"]["partial_integral"]
            b = res[f"resampled_{key}"]["partial_integral"]
            weighted_resampled[key] = {"weighted": a, "resampled": b,
                "relative_difference_percent": 100*abs(a-b)/max(abs(a), abs(b), 1e-300)}
    qcoverage = float((math.erf((M_ANCHOR[-1]-M_MU)/(M_SIG*math.sqrt(2))) -
                       math.erf((M_ANCHOR[0]-M_MU)/(M_SIG*math.sqrt(2)))) /
                      (math.erf(5/math.sqrt(2))-math.erf(-5/math.sqrt(2))))
    return {
        "schema": "J0740_F68_MPA1_PCHIP_PARTIAL_F38_EVIDENCE_V1",
        "status": "PASS_PARTIAL_APPROXIMATE_EVIDENCE_CONTRIBUTION_ONLY",
        "model": MODEL,
        "F68_actions_run_id": F68_RUN_ID,
        "F68_direct_RNS_anchor_masses_msun": M_ANCHOR.tolist(),
        "F68_direct_RNS_196_mesh_rotating_Req_km": R_ANCHOR_KM.tolist(),
        "F68_report_sha256": sha256(f68_report),
        "F38_zip_sha256": sha256(f38_zip),
        "Salmi_published_posterior_sha256": EXPECTED_SALMI_POSTERIOR_SHA256,
        "F38_zip_crc": "PASS",
        "F38_inner_manifest_files_verified": checked,
        "mass_prior": {"distribution": "normalized truncated Gaussian, applied once",
            "mu_msun": M_MU, "sigma_msun": M_SIG, "support_sigma": [-5,5],
            "prior_mass_fraction_in_integrated_interval": qcoverage},
        "integration": {"source_surface": "published Salmi posterior divided by reconstructed source effective prior (F38 approximate, bandwidth-dependent)",
            "evidence_identity": "Z_EOS/Z_source = integral (p_source(M,R|D)/pi_source(M,R)) pi_EOS(M,R) dM dR; the EOS prior uses q_radio(M) once, with no second independent photon likelihood",
            "mass_interval_msun": [float(M_ANCHOR[0]), float(M_ANCHOR[-1])],
            "outside_interval": "NOT_INTEGRATED; positive likelihood contribution cannot be set to zero",
            "curve_interpolation": "piecewise linear in mass between four direct F68 196-mesh RNS roots",
            "grid_sizes": list(N_GRID), "values": res,
            "weighted_vs_resampled": weighted_resampled},
        "limits": {"complete_EOS_evidence": "NOT_ESTABLISHED",
            "physical_EOS_acceptance": "NOT_ESTABLISHED: F67 PCHIP alternate lacks a verified physical vacuum crust and microscopic source interpretation",
            "source_native_XPSI_photon_reanalysis": "NOT_RUN",
            "full_source_nuisance_sampler": "NOT_RUN",
            "fixed_J_stability": "NOT_RUN",
            "seven_original_EOS_model_Bayes": "NOT_RUN",
            "same_photons_multiplied_twice": False}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--f38-zip", type=Path, default=F38_ZIP)
    parser.add_argument("--f68-report", type=Path, default=F68_REPORT)
    parser.add_argument("--output", type=Path, default=HERE / "MPA1_PCHIP_partial_F38_evidence_20261119.json")
    args = parser.parse_args()
    result = run(args.f38_zip, args.f68_report)
    out = args.output
    out.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))

