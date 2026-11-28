# J0740 — K2 latent mode candidate and independent synthetic stress audit

Date: 2026-11-14. **NOT a native X-PSI / NICER calculation, not an EOS posterior.**

## Source of this work

Previously independently checked native X-PSI v2 at (M,R)=(2.000 Msun,13.625 km) had **overall FAIL**, with rare high-weight samples and many numeric CDF endpoint events in broad-tail proposals. Two previously built v3 *mathematical* proposals have full-support defensive bases, and passed their own limited synthetic tests; neither had been validated against independent phase-boundary two-mode stress. Both original v3 source files are retained unchanged under `support/` and `latent/` for replay only. Their canonical versions remain in GitHub PR #317 and ChatGPT Library.

## Exact K2 exploratory mathematical proposal

`mode_v4/mode_stratified_v4.py` defines, in the original 13D standard-normal latent coordinates,

```
q(z) = 0.50 N13(0,I)
     + 0.40 * [a_minus N13(mu_minus,Sigma_minus) + a_plus N13(mu_plus,Sigma_plus)]
     + 0.10 * [a_minus N13(mu_minus,1.5 Sigma_minus) + a_plus N13(mu_plus,1.5 Sigma_plus)]
```

with `a_minus+a_plus=1`; source-normal `z2 < 0` vs `z2 >= 0` is the preselected training partition. The K2 means/covariances and mode mass are fitted on **training-only importance weights**. Gaussian components and q mixture have analytical normalizers. Safety lower bound `q(z) >= 0.5 N13(z;0,I)` holds. No proposal-density clipping, sample deletion, weight capping or X-PSI model changes. Global training ESS <64 or per-mode ESS <32 aborts. Fitting requires >=512 training rows. Regularized covariance ridge 0.10 and eigenvalue floor 0.20. No phase CDF inverse in the proposal sampler; original source prior transport **still must check** normal-CDF endpoints on every actual native draw and abort if observed. It must never silently clamp or discard.

The exact native importance log weight, **only after independently verifying source mapping** remains `logL(original_source_transform(Phi(z))) + log N13(z;0,I) - log q(z)`. The toy model in this bundle does not verify that mapping.

## RED/GREEN software test evidence

A public-method test was first observed FAIL because the two-mode fit raised `NotImplementedError`. A test for moderate broad components was later observed FAIL (3 vs 5 expected components). After implementation both tests and four further public-contract tests are **6/6 PASS** (full `unittest -v` output in `v4_unittest_pass.log`). A re-run also passes. This is software correctness only, not astrophysical validation.

## Pilot comparison (development data; NOT confirmatory)

Three analytically normalized synthetic targets: correlated Gaussian, symmetric bimodal Gaussian, and a deliberately severe two-peaked phase-edge distribution (unit-phase mapping `Phi(z2)` around 0.008 / 0.992). Pilot used 4,096 training points and 4×1,024 proposal draws per target. Both v3 designs failed frozen-style gates on the hard phase-edge target. An exploratory K2 model was then developed and refined using this **seen pilot**; the pilot success cannot be called independent evidence.

## Separate predeclared synthetic test, no further tuning

Files: `independent_synthetic_predeclared.json`, `run_independent_synthetic.py`, `independent_synthetic_results.json`. The predeclared record contains the SHA-256 frozen K2 module and frozen comparator script, unseen training seed **20261201**, test seeds **2301,2303,2307,2311**, 4096 training draws and 1024 draws per evaluation seed. Three normalized synthetic targets were fixed before this check. Thresholds reused unchanged from the historical fixed-point auxiliary gates: ESS ≥200/1024, max weight ≤0.02, half-phase ESS≥50, 512→1024 evidence drift ≤0.10, between-seed log-evidence range ≤0.15, zero CDF endpoint events. These are *diagnostic toy criteria*, not a valid native science acceptance.

| Synthetic target | K2 worst ESS | K2 worst max weight | K2 largest drift | K2 outcome |
|---|---:|---:|---:|---|
| Correlated Gaussian | 629.05 | 0.010948 | 0.01242 | PASS |
| Symmetric bimodal | 645.58 | 0.008562 | 0.02618 | PASS |
| Two phase-edge peaks | 226.67 | **0.021231** | 0.08027 | **FAIL** |

Independent synthetic K2 **overall FAIL (2/3 targets pass)** because of the strict max-weight gate on the phase-edge target, even though ESS, split drift and across-seed evidence range passed there. No gate or seed was changed after observing it. Other designs also fail the hard synthetic target on at least one gate. Do not overstate this as successful native nuisance integration or EOS inference.

## Pending science gates

- Owner Windows `DESKTOP-AT3D58I` SentinelX agent is **offline** at time of this work; no source X-PSI photons/data were accessed.
- No real training-only native K2 fitting, no new non-overlapping native held-out, no `pi_eff(M,R)` native marginalization, no full M-R convergence, no rotating-star EOS posterior.
- Before any real run, independently confirm source conditional-prior transport, model hash, 13D normalization/Jacobian and native base identity; freeze a **new** science protocol with non-colliding native seeds, training frozen proposal and unchanged acceptance gates before first heldout likelihood call.
- Both v3 candidates, K2 pilot and K2 independent synthetic failure remain preserved for reproducibility. **EOS_Bayes=NOT_RUN; full_MR_convergence=NOT_ESTABLISHED**.

## Reproduce

Python 3.12+ with NumPy and SciPy:

```
cd mode_v4
python -m unittest -v test_mode_stratified_v4.py
cd ..
python run_independent_synthetic.py
```

`run_independent_synthetic.py` verifies SHA-256 fingerprints of the candidate and comparator before executing; the JSON output is deterministic given the recorded environment/seed and source versions. CI must use compatible NumPy/SciPy; exact bitwise agreement across different math-library versions is not guaranteed. `archive_manifest.json` records the package hashes.