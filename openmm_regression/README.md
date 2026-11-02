# OpenMM regression evidence — 2026-11-02

Local Windows x64 execution; Python 3.12.10, OpenMM 8.6.1
(`b399af4725573963b46d6c1083fdcf7a37615857`), NumPy 2.5.4.
NVIDIA RTX 3060, 12 GB VRAM, driver 560.94 (driver reports CUDA 12.6).
The installed wheel exposes Reference, CPU and OpenCL, not CUDA.
OpenMM installation test and `pip check` pass. Packages downloaded successfully
from PyPI; GitHub clone succeeded with elevated network access.
Python 3.15.2 is the system default; this project uses a separate Python 3.12 venv.
Windows Store Python access requires execution as the desktop user rather than
the restricted Codex sandbox account. No system Python installation was modified.

| Issue | Stock 8.6.1 | Local patched retest | Evidence |
|---|---|---|---|
| #5532 | FAIL | PASS | 26 chains pass stock; 27 and 52 corrupt bonds. After patch all three pass with both keepIds modes. |
| #5521 | FAIL | PASS | Stock keeps water 101 only; patch keeps 101/102/103 and first conformers. Two-model test also passes. |
| #5515 | FAIL | FAIL | CPU loses 30–66 pairs at triclinic float32 boundary; orthogonal and 1e-5 controls pass. |
| #5493 | FAIL | FAIL | OpenCL single: 15/20 checkpoint force mismatches for each integrator. Position drift after 100 steps: 0.000100851 nm Verlet; 0.00192261 nm CustomIntegrator. |
| #5494 | FAIL | FAIL | CPU PME plugin available, but UseCpuPme=true emits compiler errors and produces bitwise identical forces to GPU PME; consistent with silent fallback. |
| CUDA-specific execution | SKIP | SKIP | No CUDA platform in this wheel; driver presence does not prove OpenMM CUDA availability. |

The task is **not fully resolved**: three native CPU/GPU regressions remain.
No native OpenMM C++ rebuild or upstream fix is claimed. The local Python patch
does not address #5515, #5493 or #5494. A source build with reviewed native fixes
and rerunning these same reproducers is the outstanding work.

## Reproduce

From the parent workspace (PowerShell, using an account with Windows Store Python access):

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r repo/openmm_regression/requirements.txt
.venv/Scripts/python.exe repo/openmm_regression/run_all.py
.venv/Scripts/python.exe repo/openmm_regression/finalize.py
```

`run_all.py` restores the saved stock Python parser before baseline measurements,
then applies the guarded patch and retests. It exits nonzero when scientific
assertions fail. Original reproducers print diagnostics and may exit zero even
when a bug is present; `summarize.py` checks their measurements instead.
`finalize.py` performs final parser tests, package freeze, summary and hash manifest;
it also exits nonzero while unresolved failures remain.

The venv currently contains the local parser patch. Its original is backed up
as `pdbxfile.py.original`. To restore stock behavior, copy this backup over
`pdbxfile.py`, then restart Python. Reinstalling OpenMM also removes the patch.
The patch generates unique C1/C2/... identifiers in default mmCIF output and
uses a separate, residue-aware alternate-position table, preserving struct_conn
lookup behavior. This is a scoped local fix, not an upstream release claim.

## Evidence and provenance

`results/` contains baseline/final JSON, unedited subprocess stdout/stderr,
environment identity, package freeze and SHA-256 hashes. `mmcif_fixes.patch`
records the exact local source changes. `parser_extra.py` tests multi-model waters.
`openmm_mmcif_roundtrip_regression.py` was created for this task because no
preexisting file with that name was found in the workspace or accessible Codex projects.

Reproducers and synthetic water fixture were adapted from the primary reports:

- https://github.com/openmm/openmm/issues/5532 (swf1996120)
- https://github.com/openmm/openmm/issues/5521 (shaanbdu)
- https://github.com/openmm/openmm/issues/5515 (hikarino-my)
- https://github.com/openmm/openmm/issues/5493 (RedesignedRobot)
- https://github.com/openmm/openmm/issues/5494 (RedesignedRobot)

Only local synthetic computational tests were performed. No paid service,
GitHub Actions execution, physical robot or biological experiment was initiated.
