"""F87: constant-angular-momentum RNS sequence on the original APR source EOS.

Only the pinned RNS solver's final printf is patched to expose J and M0.
The solver arithmetic remains byte-identical to upstream. A fixed-J model is
found by solving J(axis_ratio)-J_target=0 over actual RNS models, without
extrapolation. This is a sampled turning-point diagnostic, not a full
rotating dynamical stability proof or an EOS posterior calculation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

from scipy.optimize import brentq

RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
SOURCE_ARCHIVE_SHA256 = "8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12"
TARGET_RHO = 1743223916825675.2
TARGET_SPIN_HZ = 346.536369
AXIS_RATIOS = (1.0, .995, .990, .985, .980, .970, .955, .940, .920, .900)
DENSITIES_E15 = (1.45, 1.50, 1.55, 1.58, 1.60, 1.62, 1.65, 1.68,
                 1.70, 1.72, 1.743223916826, 1.76, 1.78, 1.80, 1.82, 1.8290)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def patch_rns_source(source: Path) -> dict:
    old = source.read_text(encoding="utf-8")
    original_hash = sha256_bytes(old.encode())
    pattern = r'printf\("%g \\t %4\.3f \\t %4\.2f \\t %4\.1f \\n",\s*star\.e_center, star\.Mass/MSUN, star\.R_e\*1e-5, star\.Omega/\(2\.0\*PI\)\);'
    replacement = (
        'printf("J0740_MACHINE %.17g %.17g %.17g %.17g %.17g %.17g\\n",'
        'star.e_center/(C*C*KSCALE),star.Mass/MSUN,star.R_e*1e-5,'
        'star.Omega/(2.0*PI),star.Mass_0/MSUN,star.ang_mom);'
    )
    patched, count = re.subn(pattern, lambda _match: replacement, old, count=1)
    if count != 1:
        raise ValueError(f"PINNED_RNS_OUTPUT_STATEMENT_MISMATCH:{count}")
    source.write_text(patched, encoding="utf-8", newline="\n")
    return {
        "rns_upstream_commit": RNS_COMMIT,
        "original_rns_c_sha256": original_hash,
        "patched_rns_c_sha256": sha256_bytes(patched.encode()),
        "replacements": count,
        "patch_scope": "One diagnostic printf only; upstream solver arithmetic unchanged.",
    }


def parse_machine_row(stdout: str, expected_density: float) -> dict:
    rows = []
    for line in stdout.splitlines():
        if not line.startswith("J0740_MACHINE "):
            continue
        try:
            values = [float(value) for value in line.split()[1:]]
        except ValueError:
            continue
        if len(values) == 6 and all(math.isfinite(value) for value in values):
            rows.append(values)
    if len(rows) != 1:
        raise ValueError(f"EXPECTED_ONE_MACHINE_ROW_GOT:{len(rows)}")
    density, mass, radius, spin, mass0, angular_momentum = rows[0]
    if abs(density - expected_density) > max(5e8, expected_density * 1e-6):
        raise ValueError("CENTRAL_DENSITY_ECHO_MISMATCH")
    if not (0.5 < mass < 3.5 and 7 < radius < 25 and 0 <= spin < 2000
            and mass0 > 0 and 0 <= angular_momentum < 1e53):
        raise ValueError("RNS_MODEL_RANGE_GUARD_FAILED")
    return {
        "central_energy_density_g_cm3": density,
        "mass_msun": mass,
        "radius_eq_km": radius,
        "spin_hz": spin,
        "rns_mass0_msun_uninterpreted": mass0,
        "ang_mom_cgs": angular_momentum,
    }


def run_model(binary: Path, table: Path, density: float,
              *, spin: float | None = None, axis_ratio: float | None = None) -> dict:
    if (spin is None) == (axis_ratio is None):
        raise ValueError("CHOOSE_EXACTLY_ONE_OF_SPIN_OR_AXIS_RATIO")
    command = [str(binary.resolve()), "-f", "./" + table.name,
               "-e", f"{density:.12g}"]
    if spin is not None:
        command.extend(("-s", f"{spin:.9f}"))
    else:
        command.extend(("-r", f"{axis_ratio:.10f}"))
    proc = subprocess.run(command, cwd=table.parent, capture_output=True,
                          text=True, timeout=180, check=False)
    if proc.returncode:
        raise RuntimeError(f"RNS_EXIT_{proc.returncode}:{proc.stderr[-400:]}")
    result = parse_machine_row(proc.stdout, density)
    if spin is not None and abs(result["spin_hz"] - spin) > 0.25:
        raise ValueError("FIXED_SPIN_ANCHOR_RESIDUAL_GT_0.25_HZ")
    if axis_ratio is not None:
        result["axis_ratio"] = axis_ratio
    return result


def solve_fixed_j(binary: Path, table: Path, density: float,
                  target_j: float) -> dict:
    trace = []
    previous = None
    bracket = None
    cache = {}
    for ratio in AXIS_RATIOS:
        try:
            model = run_model(binary, table, density, axis_ratio=ratio)
        except Exception as exc:
            trace.append({"axis_ratio": ratio, "status": "FAILED",
                          "reason": type(exc).__name__ + ": " + str(exc)[:180]})
            continue
        cache[ratio] = model
        trace.append({"axis_ratio": ratio, "status": "OK",
                      "ang_mom_cgs": model["ang_mom_cgs"]})
        if previous is not None and ((previous[1] - target_j)
                                     * (model["ang_mom_cgs"] - target_j) <= 0):
            bracket = (previous[0], ratio)
            break
        previous = (ratio, model["ang_mom_cgs"])
    if bracket is None:
        raise ValueError("NO_NATIVE_RNS_FIXED_J_BRACKET")

    calls = 0

    def residual(ratio: float) -> float:
        nonlocal calls
        calls += 1
        model = run_model(binary, table, density, axis_ratio=ratio)
        cache[ratio] = model
        return model["ang_mom_cgs"] / target_j - 1.0

    ratio = brentq(residual, *sorted(bracket), xtol=1e-9, rtol=1e-10,
                   maxiter=45)
    result = cache.get(ratio) or run_model(binary, table, density,
                                           axis_ratio=ratio)
    result["J_relative_residual"] = result["ang_mom_cgs"] / target_j - 1.0
    result["root_evaluations"] = calls
    result["axis_ratio_scan_trace"] = trace
    if abs(result["J_relative_residual"]) > 5e-6:
        raise ValueError("FIXED_J_RESIDUAL_GT_5E-6")
    return result


def run(source_dir: Path, binary: Path, grid: str,
        patch_report: Path, output: Path,
        target_j_override: float | None = None) -> dict:
    source_dir = source_dir.resolve()
    table = output.with_name("eosF87_compose_apr_unified")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from f87_real_rns_from_compose import write_table

    _, source_meta, cs2 = write_table(source_dir, table)
    if source_meta["source_archive_sha256"] != SOURCE_ARCHIVE_SHA256:
        raise ValueError("PUBLISHER_SOURCE_HASH_MISMATCH")
    table_sha256 = sha256_bytes(table.read_bytes())
    acausal_index = int(next(i for i, value in enumerate(cs2) if value > 1.0))
    first_acausal_rho = source_meta["first_native_acausal_energy_density_g_cm3"]
    anchor = run_model(binary, table, TARGET_RHO, spin=TARGET_SPIN_HZ)
    target_j = (anchor["ang_mom_cgs"] if target_j_override is None
                else target_j_override)
    if not 1e47 < target_j < 1e50:
        raise ValueError("ANGULAR_MOMENTUM_ANCHOR_OUT_OF_RANGE")
    if abs(anchor["ang_mom_cgs"] / target_j - 1.0) > 0.01:
        raise ValueError("FIXED_SPIN_REFERENCE_J_DIFFERS_FROM_SHARED_J_BY_GT_1_PERCENT")

    sequence = []
    for density_e15 in DENSITIES_E15:
        density = density_e15 * 1e15
        try:
            result = solve_fixed_j(binary, table, density, target_j)
            if density >= first_acausal_rho:
                raise ValueError("SAMPLE_REACHED_OR_EXCEEDED_SOURCE_ACAUSAL_KNOT")
            result.update({"status": "PASS_FIXED_J",
                           "central_energy_density_g_cm3": density})
        except Exception as exc:
            result = {"central_energy_density_g_cm3": density,
                      "status": "FAILED_FIXED_J",
                      "reason": type(exc).__name__ + ": " + str(exc)}
        sequence.append(result)

    good = sorted((item for item in sequence if item["status"] == "PASS_FIXED_J"),
                  key=lambda item: item["central_energy_density_g_cm3"])
    masses = [item["mass_msun"] for item in good]
    monotone = len(good) == len(DENSITIES_E15) and all(
        right > left for left, right in zip(masses, masses[1:]))
    if not monotone:
        status = "INCOMPLETE_OR_NONMONOTONE_NO_STABILITY_CLAIM"
    else:
        status = "PASS_SAMPLED_CONSTANT_J_SEQUENCE_NO_TURNING_POINT_AT_SAMPLED_POINTS"
    record = {
        "schema": "A01.01.50_F87_APR_ORIGINAL_CONSTANT_J_SEQUENCE_V1",
        "status": status,
        "model": "Original Salmi 2024 CompOSE APR(APR) source; no causal repair or EOS reweighting.",
        "rns_upstream_commit": RNS_COMMIT,
        "grid": grid,
        "rns_binary_sha256": sha256_bytes(binary.read_bytes()),
        "patch_report": json.loads(patch_report.read_text(encoding="utf-8")),
        "publisher_source_metadata": source_meta,
        "rns_table_sha256": table_sha256,
        "rns_table_rows": int(sum(1 for _ in table.open(encoding="ascii")) - 1),
        "fixed_spin_reference_anchor": anchor,
        "shared_target_J_override_cgs": target_j_override,
        "target_J_cgs": target_j,
        "sequence": sequence,
        "successful_points": len(good),
        "sampled_mass_strictly_increasing": monotone,
        "sampled_interval_g_cm3": ([good[0]["central_energy_density_g_cm3"],
                                      good[-1]["central_energy_density_g_cm3"]]
                                     if good else None),
        "sampled_upper_density_fraction_of_first_acausal_knot": (
            good[-1]["central_energy_density_g_cm3"] / first_acausal_rho if good else None),
        "first_native_acausal_index_in_source": acausal_index,
        "first_native_acausal_density_g_cm3": first_acausal_rho,
        "interpretation": (
            "No sampled fixed-J mass turning point is present from the lowest "
            "sampled density through 99.945% of the first source-acausal density. "
            "This is not a full rotating dynamical eigenmode calculation."
            if monotone else "Sequence incomplete or nonmonotone; no stability conclusion."),
        "EOS_Bayes": "NOT_RUN",
        "rotating_dynamical_eigenmodes": "NOT_RUN",
        "limitations": [
            "The fixed-J turning-point diagnostic does not prove nonlinear or full dynamical stability.",
            "The original source EOS is acausal above its first source-native cs2/c2 > 1 node; no result is extrapolated beyond it.",
            "This sequence is not a NICER/XMM likelihood, posterior reweighting, or final EOS acceptance.",
            "RNS M0 is recorded for reproducibility and is not reinterpreted as a physically normalized baryon mass.",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("patch", "run"), required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--grid", choices=("151x301", "201x401"))
    parser.add_argument("--patch-report", type=Path)
    parser.add_argument("--target-j", type=float)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.mode == "patch":
        if args.source is None:
            parser.error("--source is required for --mode patch")
        result = patch_rns_source(args.source)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2))
        return
    required = (args.source_dir, args.binary, args.grid, args.patch_report)
    if any(value is None for value in required):
        parser.error("--source-dir, --binary, --grid and --patch-report are required for run")
    result = run(args.source_dir, args.binary, args.grid, args.patch_report,
                 args.out, args.target_j)
    print(json.dumps({"status": result["status"],
                      "successful_points": result["successful_points"],
                      "sampled_interval_g_cm3": result["sampled_interval_g_cm3"],
                      "target_J_cgs": result["target_J_cgs"],
                      "interpretation": result["interpretation"]}, indent=2))
    if not result["status"].startswith("PASS"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
