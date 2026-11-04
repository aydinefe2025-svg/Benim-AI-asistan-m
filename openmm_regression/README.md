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

The OpenMM wheel and pinned runtime/test dependency wheels are in the parent
workspace's `dist/` directory. Keep this artifact directory with the workspace;
it is intentionally not copied into Git history. The SHA-256 manifest now
covers every wheel in the bundle. The Windows Store CPython 3.12 runtime copy
is kept in the workspace's `.runtime312/` directory, outside the Git checkout.
The setup script prefers this accessible runtime, repairs stale virtual-env
metadata without deleting packages, verifies the exact OpenMM wheel hash, then
performs an offline reinstall and full validation. Run:

```powershell
powershell -ExecutionPolicy Bypass -File repo/openmm_regression/setup_local.ps1
```

That script pins packages from local wheels and runs `pip check`, reapplies the
idempotent mmCIF parser patch, executes `openmm.testInstallation`, the 26/27/52
chain and water checks, and all five scientific regressions. It refreshes raw
logs, the JSON summary and SHA-256 manifest; the manifest is refreshed only
after every check passes. The standalone mmCIF test is:

```powershell
.venv/Scripts/python.exe repo/openmm_regression/openmm_mmcif_roundtrip_regression.py
```

The full native regression suite supports both pytest and direct execution:

```powershell
.venv/Scripts/python.exe -m pytest repo/openmm_regression/test_native.py -q -p no:cacheprovider
.venv/Scripts/python.exe repo/openmm_regression/test_native.py
```

The pytest invocation validates without rewriting the archived summary. Direct
execution refreshes `native_results/summary.json`.

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

## Recovery and artifact integrity

Use the project interpreter explicitly (`.venv/Scripts/python.exe`); the
machine-wide `python` command may select another Python version. If `.venv` is
missing, `setup_local.ps1` recreates it from `.runtime312/` or a registered
CPython 3.12. If Python, package versions, or a wheel hash does not match the
lock, the script stops before claiming success. Restore the workspace `dist/`
artifact bundle from backup before running it; no GitHub Actions, paid runner,
or online dependency resolution is required.

