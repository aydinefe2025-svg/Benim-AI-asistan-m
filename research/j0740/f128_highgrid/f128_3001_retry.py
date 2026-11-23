#!/usr/bin/env python3
"""Bounded 3001x6001 retry rooted in the validated 601x1201 fixed-J artifact."""
from __future__ import annotations
import argparse, hashlib, io, json, math, subprocess, zipfile
from pathlib import Path
from scipy.optimize import brentq
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from research.j0740.f128.f128_tight_fixedj_reroot import (
    TARGET_RHO, F124_SHA, F125_SHA, EOS_SHA, RNS_COMMIT, TIGHT_ACCURACY,
    ROOT_TOL, read_reference, parse_real_star, sha,
)

COARSE_SHA = "e099c2f07353fcdbc02dd42d94e0b6310ac96e9522d5b4917050f4ce79f56f95"
COARSE_ARTIFACT_ID = "14808314605"
CALL_TIMEOUT = 1200
MAX_CALLS_PER_DENSITY = 5
OFFSETS = (0.0, -1.0e-5, 1.0e-5, -3.0e-5, 3.0e-5)

def coarse_seeds(path: Path) -> tuple[dict[str, float], float]:
    raw = path.read_bytes()
    if sha(raw) != COARSE_SHA:
        raise ValueError("COARSE_601_ARTIFACT_SHA256_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:
            raise ValueError("COARSE_601_ARTIFACT_CRC_FAILURE")
        names = [n for n in z.namelist() if n.endswith("F128_TIGHT_FIXEDJ_REROOT_RECEIPT.json")]
        if len(names) != 1:
            raise ValueError("COARSE_601_RECEIPT_MEMBER_NOT_UNIQUE")
        receipt = json.loads(z.read(names[0]))
    if (receipt.get("status") != "FOUR_TIGHT_FIXED_J_ROOTS_COMPLETE_DIAGNOSTIC_ONLY"
        or receipt.get("EOS_sha256") != EOS_SHA
        or receipt.get("RNS_upstream_commit") != RNS_COMMIT
        or receipt.get("fixed_J_root_relative_tolerance") != ROOT_TOL):
        raise ValueError("COARSE_601_RECEIPT_INVALID")
    roots = {}
    for label, rho in TARGET_RHO.items():
        wanted = f"601x1201_{label}"
        matches = [x for x in receipt.get("results", []) if x.get("label") == wanted]
        if len(matches) != 1:
            raise ValueError("COARSE_601_ROOT_MISSING_" + label)
        item = matches[0]
        root = item.get("root", {})
        star = root.get("star", {})
        if (item.get("rho_g_cm3") != rho or root.get("status") != "REAL_C_COMPLETE"
            or root.get("J_relative_error", 1.0) > ROOT_TOL
            or star.get("rho_g_cm3") != rho):
            raise ValueError("COARSE_601_ROOT_INVALID_" + label)
        roots[label] = float(root["r_ratio"])
    return roots, float(receipt["target_J_cgs"])

def evaluate(binary: Path, eos: Path, rho: int, ratio: float, target_j: float,
             label: str, outdir: Path, calls: dict[str, dict]) -> float:
    key = f"{float(f'{ratio:.12f}'):.12f}"
    if key not in calls:
        if len(calls) >= MAX_CALLS_PER_DENSITY:
            raise RuntimeError("MAX_NATIVE_CALLS_REACHED")
        cmd = [str(binary.resolve()), "-f", str(eos), "-e", f"{rho:.14e}", "-r", key]
        row = {"ratio": float(key), "rho_g_cm3": rho, "binary_sha256": sha(binary.read_bytes())}
        stdout = stderr = ""
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=CALL_TIMEOUT, check=False)
            stdout, stderr = p.stdout, p.stderr
            if p.returncode:
                raise RuntimeError("NATIVE_C_EXIT_" + str(p.returncode))
            star = parse_real_star(stdout, stderr, rho)
            signed = star["J_cgs"] / target_j - 1.0
            row.update({"status": "REAL_C_COMPLETE", "star": star,
                        "J_signed_relative_error": signed, "J_relative_error": abs(signed),
                        "stdout_sha256": sha(stdout.encode()), "stderr_sha256": sha(stderr.encode())})
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            row.update({"status": "FAIL_CLOSED", "error": f"NATIVE_C_TIMEOUT_{CALL_TIMEOUT}S",
                        "stdout_sha256": sha(stdout.encode()), "stderr_sha256": sha(stderr.encode())})
        except Exception as exc:
            row.update({"status": "FAIL_CLOSED", "error": repr(exc),
                        "stdout_sha256": sha(stdout.encode()), "stderr_sha256": sha(stderr.encode())})
        prefix = outdir / f"{label}_{rho}_{key}"
        Path(str(prefix) + ".stdout.txt").write_text(stdout, encoding="utf-8")
        Path(str(prefix) + ".stderr.txt").write_text(stderr, encoding="utf-8")
        calls[key] = row
        with (outdir / f"{label}_{rho}_calls.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n"); f.flush()
        print("F128_HIGHGRID_NATIVE_C_CALL", json.dumps({"label": label, **row}, sort_keys=True), flush=True)
    row = calls[key]
    if row["status"] != "REAL_C_COMPLETE":
        raise RuntimeError(row["error"])
    return row["J_signed_relative_error"]

def run_density(binary: Path, eos: Path, label: str, rho: int, seed: float,
                target_j: float, outdir: Path) -> dict:
    calls: dict[str, dict] = {}
    err = None
    for offset in OFFSETS:
        try:
            evaluate(binary, eos, rho, seed + offset, target_j, label, outdir, calls)
        except Exception as exc:
            err = repr(exc)
        good = sorted((float(k), v) for k, v in calls.items() if v["status"] == "REAL_C_COMPLETE")
        bracket = next(((a, b) for (a, ra), (b, rb) in zip(good, good[1:])
                        if ra["J_signed_relative_error"] * rb["J_signed_relative_error"] < 0), None)
        best = min((v for _, v in good), key=lambda r: r["J_relative_error"], default=None)
        if best and best["J_relative_error"] <= ROOT_TOL:
            return {"label": label, "rho_g_cm3": rho, "reference_ratio_601x1201": seed,
                    "root": best, "native_C_evaluations": len(calls), "bracket_found": bracket is not None,
                    "call_rows": list(calls.values())}
        if bracket:
            try:
                remaining = MAX_CALLS_PER_DENSITY - len(calls)
                root_ratio = brentq(lambda x: evaluate(binary, eos, rho, x, target_j, label, outdir, calls),
                                    bracket[0], bracket[1], xtol=1e-12, rtol=5e-14,
                                    maxiter=max(1, remaining))
                evaluate(binary, eos, rho, root_ratio, target_j, label, outdir, calls)
                best = min((v for v in calls.values() if v["status"] == "REAL_C_COMPLETE"),
                           key=lambda r: r["J_relative_error"])
                if best["J_relative_error"] <= ROOT_TOL:
                    return {"label": label, "rho_g_cm3": rho, "reference_ratio_601x1201": seed,
                            "root": best, "native_C_evaluations": len(calls), "bracket_found": True,
                            "call_rows": list(calls.values())}
            except Exception as exc:
                err = repr(exc)
            break
    return {"label": label, "rho_g_cm3": rho, "reference_ratio_601x1201": seed,
            "status": "FAIL_CLOSED", "error": err or "FIXED_J_ROOT_NOT_FOUND_WITHIN_CALL_CAP",
            "native_C_evaluations": len(calls), "call_rows": list(calls.values())}

def main() -> None:
    p = argparse.ArgumentParser()
    for name in ("f124", "f125", "coarse", "eos", "rns3001", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args(); a.out.parent.mkdir(parents=True, exist_ok=True)
    seeds, target_j = coarse_seeds(a.coarse)
    refs = {}
    for label, path, expected in (("F124", a.f124, F124_SHA), ("F125", a.f125, F125_SHA)):
        root, target = read_reference(path, expected, label); refs[label] = root
        if target != target_j: raise ValueError("F124_F125_COARSE_TARGET_J_MISMATCH")
    if sha(a.eos.read_bytes()) != EOS_SHA: raise ValueError("F99_DERIVED_EOS_SHA256_MISMATCH")
    results=[]
    for label in ("F125", "F124"):
        results.append(run_density(a.rns3001, a.eos, "3001x6001_"+label, TARGET_RHO[label],
                                   seeds[label], target_j, a.out.parent))
    complete = all(x.get("root", {}).get("J_relative_error", 1.0) <= ROOT_TOL for x in results)
    comparisons={}
    if complete:
        by={x["label"].split("_")[-1]:x for x in results}
        for label in ("F125", "F124"):
            star=by[label]["root"]["star"]
            coarse=next(x["root"]["star"] for x in json.loads(zipfile.ZipFile(a.coarse).read(
                next(n for n in zipfile.ZipFile(a.coarse).namelist() if n.endswith("F128_TIGHT_FIXEDJ_REROOT_RECEIPT.json"))))["results"] if x["label"]=="601x1201_"+label)
            comparisons[label]={"mass_3001_minus_601_Msun":star["M_msun"]-coarse["M_msun"],
                               "radius_3001_minus_601_km":star["R_eq_km"]-coarse["R_eq_km"],
                               "J_relative_error":by[label]["root"]["J_relative_error"]}
    receipt={"schema":"J0740_F128_3001x6001_BOUNDED_FIXEDJ_RETRY_V1",
      "status":"TWO_HIGHGRID_FIXED_J_ROOTS_COMPLETE_DIAGNOSTIC_ONLY" if complete else "FAIL_CLOSED",
      "EOS_sha256":EOS_SHA,"RNS_upstream_commit":RNS_COMMIT,"coarse_artifact_id":COARSE_ARTIFACT_ID,
      "coarse_artifact_sha256":COARSE_SHA,"target_J_cgs":target_j,"mesh":"3001x6001",
      "native_call_timeout_seconds":CALL_TIMEOUT,"max_calls_per_density":MAX_CALLS_PER_DENSITY,
      "density_points_g_cm3":list(TARGET_RHO.values()),"results":results,
      "comparisons_to_601x1201":comparisons,
      "claim_limit":"Fixed-J roots on two neighboring densities only; diagnostic mesh comparison, not EOS/NICER posterior certification or full Einstein-equation/stability proof."}
    if a.out.exists(): raise FileExistsError("REFUSE_OVERWRITE_HIGHGRID_RECEIPT")
    a.out.write_text(json.dumps(receipt,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
    print("F128_HIGHGRID_RESULT",json.dumps({"status":receipt["status"],"comparisons":comparisons},sort_keys=True),flush=True)
    if not complete: raise SystemExit(2)

if __name__ == "__main__": main()
