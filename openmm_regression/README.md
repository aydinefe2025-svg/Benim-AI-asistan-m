# OpenMM locally patched Windows build

Verified on 2026-11-03 with Python 3.12.10, NumPy 2.5.4, NVIDIA RTX 3060
(12 GB), and driver 560.94 / CUDA 12.6. This is a local build based on the
OpenMM source revision recorded in `native_results/summary.json`; it is not an
upstream release. Its package version is `8.6.1+local.20261103`.

## Verified outcome

| Issue | Result | Validation |
|---|---|---|
| #5532 | PASS | mmCIF round trips with 26, 27 and 52 chains, with `keepIds` both false and true; atom identities, bonds and positions preserved. |
| #5521 | PASS | Waters 101, 102 and 103 retained; alternate conformers and a two-model case pass. |
| #5515 | PASS | CPU neighbor pairs match Reference for all 30 tested triclinic boundary cases. |
| #5493 | PASS | OpenCL and CUDA, built-in and custom integrators: zero checkpoint force mismatches and zero position drift after 100 steps. |
| #5494 | PASS | OpenCL and CUDA CPU-PME paths match Reference within force/energy tolerance; force groups, charge updates and no-silent-fallback checks pass. |

All four OpenMM platforms (Reference, CPU, OpenCL, CUDA) pass
`openmm.testInstallation`. The upstream C++ suite passed 21/21 selected CPU,
OpenCL and CUDA tests. The complete machine-readable results and raw logs are
in `native_results/`. `results/` preserves the original stock-wheel baseline;
it intentionally records the failures that motivated these fixes.

## Install the verified wheel

The local wheel and pinned NVIDIA runtime wheels are in the parent workspace's
`dist/` directory. On the machine used for verification, run:

```powershell
powershell -ExecutionPolicy Bypass -File repo/openmm_regression/setup_local.ps1
```

That script installs offline, runs `pip check`, and repeats all five scientific
regression checks. The standalone mmCIF test is:

```powershell
.venv/Scripts/python.exe repo/openmm_regression/openmm_mmcif_roundtrip_regression.py
```

The wheel is Windows x64 / CPython 3.12 specific and the CUDA plugin requires a
working NVIDIA driver. `native_results/wheel.json` records its SHA-256. The
source patch is `native_fixes.patch`; native build and installation scripts are
in this directory. The mmCIF parser edit is applied to the venv by
`apply_mmcif_fixes.py` and its original is saved as `pdbxfile.py.original`.
The wheel keeps the RPMD plugin DLLs from the matching 8.6.1 Python package;
the newer source-tree RPMD class ABI does not match that prebuilt Python
extension, and RPMD is outside these five regression fixes.

Only local synthetic computational tests were performed. No paid service,
GitHub Actions run, physical robot or biological experiment was initiated.
