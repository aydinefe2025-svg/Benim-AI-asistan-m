"""Independent uniformly rotating GR solver preflight for J0740, NOT EOS inference.

Uses upstream RNS source + eosAPR table pinned to fixed commits.
WARNING: rns-alberta/eos/eosAPR is not equal to JESTER/LALSuite APR4_EPP.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess

RNS_REPO = "rns-alberta/rns"
RNS_COMMIT = "97e85d325a33e37f702306414533f6cd77812477"
EOS_REPO = "rns-alberta/eos"
EOS_COMMIT = "7ef71a578d2e52dede24bce055839f2b74f43721"
OBSERVED_SPIN_HZ = 346.536369
EOS_LABEL = "rns-alberta/eos/eosAPR"
# Published upstream example: e_c = 1e15 g/cm3, spin = 300 Hz,
# M = 1.453 Msun, R_eq=11.48 km (reported rounded precision).
REFERENCE = {"e_c": 1.0e15, "spin_hz": 300.0, "mass_msun": 1.453, "radius_eq_km": 11.48}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_rns_output(stdout: str, *, central_density: float, requested_spin_hz: float) -> dict:
    """Parse only the RNS final four-column physical row, reject invalid output."""
    rows = []
    for line in stdout.splitlines():
        split = line.split()
        if len(split) != 4:
            continue
        try:
            values = [float(x) for x in split]
        except ValueError:
            continue
        if all(math.isfinite(v) for v in values):
            rows.append(values)
    if len(rows) != 1:
        raise ValueError(f"Expected exactly one finite numeric RNS output row; got {len(rows)}; stdout_tail={stdout[-1200:]!r}")
    e15, mass, radius, freq = rows[0]
    if not (0.5 < mass < 3.5 and 7.0 < radius < 25):
        raise ValueError("Unphysical RNS mass/radius; do not interpret output")
    if not (math.isclose(e15, central_density / 1.0e15, abs_tol=5e-4, rel_tol=5e-4)):
        raise ValueError("Wrong central energy density in RNS output")
    # The upstream RNS executable prints the spin rounded to 0.1 Hz.
    if abs(freq - requested_spin_hz) > 0.10:
        raise ValueError("Rotating GR spin mismatch")
    return {"central_energy_density_g_cm3": central_density, "mass_msun": mass,
            "radius_eq_km": radius, "spin_hz_reported": freq,
            "requested_spin_hz": requested_spin_hz}


def run_rns(binary: Path, eos_file: Path, *, central_density: float, spin_hz: float, timeout: int = 180) -> dict:
    if not (math.isfinite(central_density) and central_density > 0):
        raise ValueError("central energy density must be positive")
    if not (math.isfinite(spin_hz) and 0 <= spin_hz < 1000):
        raise ValueError("spin must be in plausible nonnegative frequency range")
    result = subprocess.run([str(binary.resolve()), "-f", str(eos_file.resolve()), "-e",
                             f"{central_density:.12g}", "-s", f"{spin_hz:.9f}"],
                            text=True, capture_output=True, timeout=timeout, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"RNS process exit {result.returncode}: {result.stderr[-1500:]}")
    parsed = parse_rns_output(result.stdout, central_density=central_density,requested_spin_hz=spin_hz)
    parsed["raw_stdout_tail"] = result.stdout[-1100:]
    return parsed


def benchmark(binary: Path, eos: Path) -> dict:
    """Do not interpret this eosAPR smoke test as an APR4_EPP or J0740 posterior."""
    for p in (binary, eos):
        if not p.is_file():
            raise FileNotFoundError(p)
    control = run_rns(binary, eos, central_density=REFERENCE["e_c"], spin_hz=300.0)
    if abs(control["mass_msun"] - REFERENCE["mass_msun"]) > 0.05:
        raise AssertionError("Published RNS e_c 1e15/300Hz mass benchmark not reproduced")
    if abs(control["radius_eq_km"] - REFERENCE["radius_eq_km"]) > 0.40:
        raise AssertionError("Published RNS e_c 1e15/300Hz radius benchmark not reproduced")
    static = run_rns(binary, eos, central_density=REFERENCE["e_c"], spin_hz=0.0)
    rotating = run_rns(binary, eos, central_density=REFERENCE["e_c"], spin_hz=OBSERVED_SPIN_HZ)
    if rotating["radius_eq_km"] <= static["radius_eq_km"]:
        raise AssertionError("Expected rotating equatorial radius expansion at fixed central energy density")
    if rotating["mass_msun"] < static["mass_msun"]:
        raise AssertionError("Expected rotating gravitational mass not to shrink at fixed central energy density")
    return {
        "status": "EXACT_GR_RNS_SOLVER_VALIDATION_ONLY_NOT_J0740_EOS_INFERENCE",
        "physics": "full axisymmetric uniformly rotating GR, at fixed central energy density",
        "rns_repo": RNS_REPO, "rns_commit": RNS_COMMIT,
        "eos_repo": EOS_REPO, "eos_commit": EOS_COMMIT,
        "eos_label": EOS_LABEL, "eos_sha256": sha256_file(eos),
        "rns_executable_sha256": sha256_file(binary),
        "warning": "Upstream eosAPR is not the original seven JESTER EOS and is not interchangeable with APR4_EPP. Control model is ~1.45 Msun, NOT PSR J0740 mass.",
        "published_300hz_control": control,
        "same_central_density_0hz": static,
        "same_central_density_j0740_spin_346hz": rotating,
        "radius_expansion_km": round(rotating["radius_eq_km"]-static["radius_eq_km"], 6),
        "mass_increase_msun": round(rotating["mass_msun"]-static["mass_msun"], 6),
        "not_done": ["RNS same-EOS JESTER7 thermodynamic table conversion + validation",
                      "full M≈2.073 Msun RNS rotating sequences at fixed spin",
                      "XPSI event-level likelihood and native nuisance marginal prior",
                      "fully normalized EOS Bayesian evidence, selection/central density prior"]
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rns", type=Path, required=True)
    parser.add_argument("--eos", type=Path, required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    ans=benchmark(args.rns,args.eos)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(ans,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in ans.items() if k not in ("published_300hz_control", "same_central_density_0hz", "same_central_density_j0740_spin_346hz")},indent=2))
    print("MODELS:\n",json.dumps({k:ans[k] for k in ("published_300hz_control", "same_central_density_0hz", "same_central_density_j0740_spin_346hz")},indent=2))

if __name__=="__main__":
    main()
