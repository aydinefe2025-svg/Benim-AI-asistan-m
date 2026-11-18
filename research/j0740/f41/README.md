# PSR J0740+6620 EOS — F41 independent RNS-curve reconciliation + seven-source admissibility gate

**Date:** 18 November 2026. **Status:** `PASS_NUMERICAL_CROSS_CHECK_NOT_SEVEN_EOS_BAYES`.

## What was newly computed (not a copy of F39/F40)

- Read and SHA256-verified existing original **F38**, **F39** and independently computed **165-root RNS** ZIP artifacts. All three ZIP CRC checks PASS. No 12.9 GB NICER or 40 MB Salmi original re-download, no repeated GR solver run.
- Selected only strictly increasing `M(rho_c)` branch in original **central-density** order from the 165-root data. Numerical mass reversals near the turning point are not sorted into a fake stable branch.
- Interpolated the 165-root `R_eq(M)` *only* over the F39 25 masses `[1.92, 2.15] M_sun`. Cross-curve **max absolute radius difference 10.682451 metres**; median 0.323062 m, RMS 2.181946 m, at exactly 25 matched mass values.
- Re-evaluated all **six** SHA-pinned Salmi F38 `L(M,R)/Z` grids on each of the two curves with identical F39 window-normalized radio-mass density. Replicated original F39 integrals exactly (tolerance <1e-10); maximum independent-curve relative likelihood integral difference **0.034870%**.
- **12/12 Python unit tests PASS**, including archive locks, shape/mask checks, strictly rising branch, corrupted source rejection, model-source SHA inequivalence and no-final-EOS-posterior guard.

## Crucial source identity warning

F39 RNS EOS table SHA256: `e3ce6c6f314ea40e2dd3f5f1593ccb552516977bc005a5242e2629d4ba5398b7`.

165-root source RNS EOS table SHA256: `affeeaadb03c578acba17e1992f299850abfbbdee50314268acb93692a7f1d89`.

They **differ**. Thus geometrical concordance is a powerful numerical cross-check, **not** proof that the physical models/tables are identical. Neither turns source-native low-density crust, absolute baryon normalization `mu0`, global stability nor full original APR4 causality into validated results.

## Same-mass-measure F38 integral comparison — diagnostic only

| F38 grid | F39 25-direct (conditional L/Z) | 165-root interpolated (same conditional L/Z) | change |
|---|---:|---:|---:|
| `resampled_0.015_0.20.npz` | 0.6442908341 | 0.6442463618 | -0.00690% |
| `resampled_0.025_0.35.npz` | 0.7083475971 | 0.7084722319 | +0.01760% |
| `resampled_0.040_0.50.npz` | 0.7645125759 | 0.7647791650 | +0.03487% |
| `weighted_0.015_0.20.npz` | 0.6458761376 | 0.6458251280 | -0.00790% |
| `weighted_0.025_0.35.npz` | 0.7090184257 | 0.7091413242 | +0.01733% |
| `weighted_0.040_0.50.npz` | 0.7650351787 | 0.7653011198 | +0.03476% |

These numbers use the exact common `[1.92,2.15] M_sun` normalized mass window and **must not be compared unadjusted** with the separately published 165-root full-mass-support integral (0.567351, 0.625970, 0.690560), which integrates a different mass range and treats unsupported masses as zero. The independent 165-root sweep covers **91.0940%** of the ±5σ radio prior on its sampled rising branch; the remaining mass contribution/physical stability still requires model-specific handling.

## Source-native JESTER 7-EOS whole-tabulation physical input gate

Exactly pinned JESTER `e6768650ce992abfd1153a6833857572fe5cd230` source-audit artifact; no source EOS table is silently modified.

| Original JESTER source EOS | Sampled within-star gate | Whole-source `cs²<=0` nodes | Whole-source `cs²>1` nodes | Whole-table finite-node screen |
|---|---|---:|---:|---|
| APR4_EPP | PASS (sampled) | 0 | 2 | FAIL |
| ENG | FAIL | 1 | 58 | FAIL |
| MPA1 | FAIL | 1 | 0 | FAIL |
| MS1 | FAIL | 1 | 0 | FAIL |
| MS1B | FAIL | 1 | 0 | FAIL |
| WFF1 | FAIL | 1 | 69 | FAIL |
| WFF2 | FAIL | 1 | 78 | FAIL |

**Interpretation:** 1/7 (APR4_EPP) passes the *earlier sampled within-star* screen; **0/7** exact raw published tables pass the full tabulation's finite-node sound-speed/monotonicity screen. Failing source tabulations are not scientifically equivalent to disproving the underlying nuclear-matter EOS family. Passing even all sampled nodes would *not* certify continuous physics or stable rotating-star sequences. The source 7-model physically admissible prior set **has not been established**. Renaming locally modified tables `APR4_EPP`, `ENG`, etc. without stating the new construction would misstate the inference. The physical EOS *family* and priors must be explicitly specified before computing meaningful seven-model posterior probabilities.

## Result and next physically necessary computation

- `F41_MR_CURVE_AND_SIX_LIKELIHOOD_CROSSCHECK=PASS`
- `SOURCE_NATIVE_7EOS_FULL_TABLE_SAMPLE_GATE=0_OF_7_CLEAN` (failure of source table screen, *not* observational exclusion)
- `NEW_SIX_THERMODYNAMICALLY_CONSISTENT_CAUSAL_EOS_CANDIDATES=NOT_RUN`
- `FULL_STABLE_BRANCH_PHYSICS=NOT_ESTABLISHED`
- `NATIVE_COMPILED_XPSI_PHOTON_REEVALUATION=NOT_RUN`
- `FINAL_SEVEN_EOS_MODEL_BAYES=NOT_RUN`

**Priority:** construct explicitly named, thermodynamically integrated, causal seven-model *candidate* EOS family and check native crust, `c_s²`, first law, physically normalized baryon density, independently verified static TOV then rotating full-GR stability and curve. Apply the same agreed mass/population prior and F38 source-derived likelihood, with KDE/alternative analysis sensitivities and complete posterior normalization. Only after scientific acceptances should a Bayes winner be reported.

## Source lineage & exact reproduction

- [GitHub issue #280 — F39](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/280#issuecomment-6971834849)
- [Independent 165-root run #44256261379](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44256261379), artifact `14408011818`
- [Seven-source global audit GitHub workflow](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/280)
- Archive SHA256: F38 `4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307`; F39 `6402c4fd97baf1b0766e1f1d5ccb3642b5b50de2d87789f50277b916896033c2`; 165-root `2c12790459c62c3d758dcbe8e3a425cec6f8328dec3c6701af28e1ca13a96d5c`.

To rerun: supply three original ZIPs and the archived `J0740_FULL_SOURCE_NATIVE_7EOS_GATE_20261116.json` via `python f41_curve_reconciliation.py --f39 ... --f38 ... --roots165 ... --source-gate ... --out F41_result.json`, then run `python -m unittest -v test_f41_curve_reconciliation.py`. The F41 package intentionally does not duplicate raw source archives.