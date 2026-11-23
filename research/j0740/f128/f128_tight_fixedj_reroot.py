#!/usr/bin/env python3
"""F128: re-root the F124/F125 densities at fixed J with tighter native RNS-C iteration tolerance."""
from __future__ import annotations
import argparse, hashlib, io, json, math, subprocess, zipfile
from pathlib import Path
from scipy.optimize import brentq

TARGET_RHO = {"F125": 2622286757812500, "F124": 2622286765625000}
F124_SHA = "d82d43d5b72d9d2f7e7ee90f4163bf308905ec2dfca9d5c709885976e42fb196"
F125_SHA = "c975a6cac8f841e2f4640990042d26a6bed263f90083a7b3d254f426866d82f5"
EOS_SHA = "c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
TIGHT_ACCURACY = 1.0e-7
ROOT_TOL = 1.0e-9
CALL_TIMEOUT = 600

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def read_reference(path: Path, expected_sha: str, label: str) -> tuple[dict, float]:
    raw = path.read_bytes()
    if sha(raw) != expected_sha:
        raise ValueError(label + "_ARTIFACT_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:
            raise ValueError(label + "_ARTIFACT_CRC_FAILURE")
        member = f"{label}/{label}_LOWER_HALF_BISECTION.json" if label == "F125" else "F124/F124_LOWER_HALF_BISECTION.json"
        result = json.loads(z.read(member))
        journal_member = f"{label}/{label}_LOWER_HALF_BISECTION.jsonl" if label == "F125" else "F124/F124_LOWER_HALF_BISECTION.jsonl"
        rows = [json.loads(x) for x in z.read(journal_member).decode().splitlines() if x.strip()]
    if label == "F124":
        expected_status = "F124_LOWER_HALF_BISECTION_COMPLETE"
    else:
        expected_status = "F125_LOWER_HALF_BISECTION_COMPLETE"
    roots = result.get("fixed_J_solutions", [])
    if (result.get("status") != expected_status or len(roots) != 1 or not rows
            or result.get("EOS_sha256") != EOS_SHA or result.get("mesh") != "3001x6001"
            or int(roots[0].get("rho_g_cm3", -1)) != TARGET_RHO[label]
            or roots[0].get("J_relative_error", 1.0) > ROOT_TOL):
        raise ValueError(label + "_REFERENCE_ROOT_INVALID")
    root = roots[0]
    best = min(rows, key=lambda r: r.get("J_relative_error", 1.0))
    if (root.get("M_msun") != best.get("M_msun")
            or root.get("selected_r_ratio") != best.get("r_ratio_C_input")
            or root.get("J_relative_error") != best.get("J_relative_error")):
        raise ValueError(label + "_REFERENCE_ROOT_JOURNAL_MISMATCH")
    return root, float(result["target_J_cgs"])

def parse_real_star(stdout: str, stderr: str, rho: int) -> dict:
    stars = []
    for line in stdout.splitlines():
        cols = line.split()
        if len(cols) != 5:
            continue
        try:
            vals = [float(x) for x in cols]
        except ValueError:
            continue
        if not all(math.isfinite(x) and x > 0 for x in vals):
            raise ValueError("NONFINITE_OR_NONPHYSICAL_NATIVE_STAR")
        stars.append(vals)
    if len(stars) != 1:
        raise ValueError("EXPECTED_ONE_FIVE_COLUMN_NATIVE_STAR")
    rho15, mass, radius, frequency, J = stars[0]
    if abs(rho15 * 1e15 / rho - 1.0) > 1e-9:
        raise ValueError("NATIVE_CENTRAL_DENSITY_MISMATCH")
    rows = []
    for line in stderr.splitlines():
        if "F127_SPIN_FINAL_DIFFERENCE" not in line:
            continue
        fields = line.split()
        if (len(fields) != 8 or fields[0] != "F127_SPIN_FINAL_DIFFERENCE"
                or fields[2] != "ITERATIONS" or fields[4] != "ACCURACY" or fields[6] != "ACHECK"):
            raise ValueError("MALFORMED_FINAL_ITERATION_DIAGNOSTIC")
        row = {"dif": float(fields[1]), "iterations": int(fields[3]),
               "accuracy": float(fields[5]), "a_check": int(fields[7])}
        if not all(math.isfinite(row[k]) for k in ("dif", "accuracy")):
            raise ValueError("NONFINITE_FINAL_ITERATION_DIAGNOSTIC")
        rows.append(row)
    if len(rows) != 2:
        raise ValueError("EXPECTED_ONE_TERMINAL_DIAGNOSTIC_PER_SPIN_CALL")
    final = rows[-1]
    if (final["a_check"] != 0 or final["iterations"] < 2
            or final["accuracy"] != TIGHT_ACCURACY or final["dif"] < 0
            or final["dif"] > TIGHT_ACCURACY):
        raise ValueError("TIGHT_RNS_SPIN_STEP_NOT_CONVERGED")
    return {"M_msun": mass, "R_eq_km": radius, "f_hz": frequency, "J_cgs": J,
            "rho_g_cm3": rho, "last_spin_step_relative_change": final["dif"],
            "last_spin_iterations": final["iterations"], "spin_accuracy": final["accuracy"],
            "spin_call_diagnostic_rows": len(rows), "a_check": final["a_check"]}

def run_point(binary: Path, eos: Path, label: str, rho: int, seed: float,
              target_J: float, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    calls: dict[str, dict] = {}
    def evaluate(ratio: float) -> float:
        ratio_in = float(f"{ratio:.12f}")
        key = f"{ratio_in:.12f}"
        if key not in calls:
            cmd = [str(binary.resolve()), "-f", str(eos), "-e", f"{rho:.14e}", "-r", key]
            row = {"r_ratio": ratio_in, "rho_g_cm3": rho, "binary_sha256": sha(binary.read_bytes())}
            stdout = stderr = ""
            try:
                p = subprocess.run(cmd, capture_output=True, text=True, timeout=CALL_TIMEOUT, check=False)
                stdout, stderr = p.stdout, p.stderr
                if p.returncode:
                    raise RuntimeError("NATIVE_C_EXIT_" + str(p.returncode))
                star = parse_real_star(stdout, stderr, rho)
                signed = star["J_cgs"] / target_J - 1.0
                row.update({"status": "REAL_C_COMPLETE", "star": star,
                            "J_signed_relative_error": signed,
                            "J_relative_error": abs(signed),
                            "stdout_sha256": sha(stdout.encode()),
                            "stderr_sha256": sha(stderr.encode())})
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                row.update({"status": "FAIL_CLOSED", "error": "NATIVE_C_TIMEOUT_600S",
                            "stdout_sha256": sha(stdout.encode()), "stderr_sha256": sha(stderr.encode())})
            except Exception as exc:
                row.update({"status": "FAIL_CLOSED", "error": repr(exc),
                            "stdout_sha256": sha(stdout.encode()), "stderr_sha256": sha(stderr.encode())})
            prefix = outdir / f"{label}_{rho}_{key}"
            Path(str(prefix) + ".stdout.txt").write_text(stdout, encoding="utf-8")
            Path(str(prefix) + ".stderr.txt").write_text(stderr, encoding="utf-8")
            calls[key] = row
            with (outdir / f"{label}_{rho}_calls.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
                f.flush()
            print("F128_NATIVE_C_CALL", json.dumps({"label": label, **row}, sort_keys=True), flush=True)
        row = calls[key]
        if row["status"] != "REAL_C_COMPLETE":
            raise RuntimeError(row["error"])
        return row["J_signed_relative_error"]

    samples = []
    # Start with the previous fixed-J seed and a broad, symmetric local bracket.
    for offset in (0.0, -1.0e-4, 1.0e-4, -3.0e-4, 3.0e-4):
        x = seed + offset
        try:
            evaluate(x)
        except Exception as exc:
            samples.append({"ratio": x, "error": repr(exc)})
        ordered = sorted((float(k), v) for k, v in calls.items() if v["status"] == "REAL_C_COMPLETE")
        bracket = next(((a, b) for (a, ra), (b, rb) in zip(ordered, ordered[1:])
                        if ra["J_signed_relative_error"] * rb["J_signed_relative_error"] < 0), None)
        if bracket:
            break
        if any(v.get("J_relative_error", 1.0) <= ROOT_TOL for v in calls.values()):
            break
    ordered = sorted((float(k), v) for k, v in calls.items() if v["status"] == "REAL_C_COMPLETE")
    best = min((v for _, v in ordered), key=lambda r: r.get("J_relative_error", 1.0), default=None)
    bracket = next(((a, b) for (a, ra), (b, rb) in zip(ordered, ordered[1:])
                    if ra["J_signed_relative_error"] * rb["J_signed_relative_error"] < 0), None)
    if best and best["J_relative_error"] <= ROOT_TOL:
        selected = best
    elif bracket:
        try:
            root_ratio = brentq(evaluate, bracket[0], bracket[1], xtol=1e-12, rtol=5e-14, maxiter=60)
            evaluate(root_ratio)
            selected = min((v for v in calls.values() if v["status"] == "REAL_C_COMPLETE"),
                           key=lambda r: r["J_relative_error"])
        except Exception as exc:
            raise RuntimeError(f"{label}_{rho}_FIXED_J_ROOT_FAILED:{exc!r}") from exc
    else:
        raise RuntimeError(f"{label}_{rho}_FIXED_J_SIGN_BRACKET_NOT_FOUND; calls={len(calls)}; seed={seed}")
    if selected["J_relative_error"] > ROOT_TOL:
        raise RuntimeError(f"{label}_{rho}_FIXED_J_PRECISION_FAIL:{selected['J_relative_error']}")
    return {"label": label, "rho_g_cm3": rho, "reference_ratio": seed,
            "selected_r_ratio": selected["r_ratio"], "root": selected,
            "native_C_evaluations": len(calls), "call_rows": list(calls.values()),
            "bracket_found": bracket is not None, "rejected_seeds": samples}

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--f124", type=Path, required=True)
    p.add_argument("--f125", type=Path, required=True)
    p.add_argument("--eos", type=Path, required=True)
    p.add_argument("--rns151", type=Path, required=True)
    p.add_argument("--rns3001", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if sha(a.eos.read_bytes()) != EOS_SHA:
        raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    roots = {}
    for label, path, expected in (("F124", a.f124, F124_SHA), ("F125", a.f125, F125_SHA)):
        root, target = read_reference(path, expected, label)
        roots[label] = root
        if label == "F124":
            target_J = target
        elif target != target_J:
            raise ValueError("REFERENCE_TARGET_J_MISMATCH")
    results = []
    for grid_label, binary in (("151x301", a.rns151), ("3001x6001", a.rns3001)):
        for label in ("F125", "F124"):
            rho = TARGET_RHO[label]
            results.append(run_point(binary, a.eos, f"{grid_label}_{label}", rho,
                                     float(roots[label]["selected_r_ratio"]), target_J, a.out.parent))
    comparisons = {}
    for point in results:
        name = point["label"]
        target_label = name.split("_")[-1]
        comparisons[name] = {
            "mass_minus_original_Msun": point["root"]["star"]["M_msun"] - roots[target_label]["M_msun"],
            "radius_minus_original_km": point["root"]["star"]["R_eq_km"] - roots[target_label]["R_eq_km"],
            "target_J_relative_error": point["root"]["J_relative_error"],
        }
    accepted = len(results) == 4 and all(x["root"]["J_relative_error"] <= ROOT_TOL for x in results)
    receipt = {
        "schema": "J0740_F128_TIGHT_TOLERANCE_FIXED_J_REROOT_TWO_DENSITIES_TWO_MESHES_V1",
        "status": "FOUR_TIGHT_FIXED_J_ROOTS_COMPLETE_DIAGNOSTIC_ONLY" if accepted else "FAIL_CLOSED",
        "EOS_sha256": EOS_SHA, "RNS_upstream_commit": RNS_COMMIT,
        "F124_artifact_sha256": F124_SHA, "F125_artifact_sha256": F125_SHA,
        "target_J_cgs": target_J, "inner_spin_radius_step_accuracy": TIGHT_ACCURACY,
        "fixed_J_root_relative_tolerance": ROOT_TOL,
        "density_points_g_cm3": list(TARGET_RHO.values()), "results": results,
        "comparison_to_previous_1e-4_results": comparisons,
        "claim_limit": "The inner radius-iterate stop is tightened and J is re-rooted on two meshes at two fixed densities. This is not a GRV2/GRV3 virial residual, full Einstein-equation certification, dynamical stability analysis, or original-seven-EOS NICER/XMM photon Bayes result."
    }
    if a.out.exists():
        raise FileExistsError("REFUSE_OVERWRITE_F128_RECEIPT")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print("F128_RESULT", json.dumps({"status": receipt["status"], "comparisons": comparisons}, sort_keys=True), flush=True)
    if not accepted:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
