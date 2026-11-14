# PSR J0740+6620 — support-aware rare-tail proposal, v3 mathematical candidate

**A01.01.50 / A01.01.51. Status: SYNTHETIC MATH PASS; NATIVE X-PSI NOT TESTED; EOS_Bayes NOT_RUN.**

This package is the next **proposed** numerical component after the completed but **FAILED** native v1 and v2 fixed-point tests for `(M,R)=(2.000 solar masses,13.625 km)`. It is not a final density-estimator fit to NICER/XMM observations, and must not be labeled a solved EOS posterior. Windows DESKTOP-AT3D58I was offline during this mathematical development.

## Measured motivation

- V2 fixed-point, 6144 new draws; 4 held-out seeds produced two PASS/two FAIL at ESS≥200, maxW≤.02, phase ESS≥50, half→full logI drift≤.1, seed logI range≤.15.
- On v2 held-out, 50% native base draws carried about 87–90% of normalized importance mass; dominant FAIL draws came from base, not tail.
- The ×16 broad-tail component produced 96 of 99 observed `ENDPOINT` events and contributed negligible observed importance mass.
- An alternate normalization-aware candidate can therefore be evaluated without more indiscriminate tail broadening.

## New mathematical design

The source latent variable remains **13D standard-normal-prior coordinates** `z`; **source prior, source transform, physical support and likelihood are untouched**. An independently normalized native base proposal `q_base(z)` is kept with strictly positive mixture weight `0.75`. Two trainable components are Gaussian in a new auxiliary variable `y`, mapped to bounded `z`:

`z_j = B * tanh(y_j/B)`, with `B=7.0`; its exact invertible Jacobian is included:

`log q_bounded(z) = log Normal(y;mu,Sigma) - sum_j log(1-(z_j/B)^2)`, `y_j=B*atanh(z_j/B)`, for `|z_j|<B`; otherwise this component has zero density.

The full mixture is `q=0.75*q_base +0.20*q_core +0.05*q_broad` with `broad covariance = 1.6*core covariance` (no training samples discarded/clipped). This is normalized **if** the supplied native base has a correct full-support normalized density. The native base covers all finite original 13D `z`, including outside the bounded fitted components, so the fit does not truncate the source target. The bounded transforms place their samples within `|z|<7`, which avoids `Phi(z)` floating-point saturation at 0 or 1 for adapted components. The algorithm **aborts** if floating-point rounding ever saturates the tanh transform; it does not silently clip, drop or reweight any generated sample.

The current fit is a single full-covariance 13D Gaussian (not a 2D torus-conditional multimodal mixture). It is **only a mathematical candidate**; the next scientific task is source-native adapter auditing and training-only fitting, then prospective held-out seeds. It could still fail on real phase multimodality or local support; no claim of improved real-data ESS is made.

**Integration contract:** Native `base.from_unit` must accept an `(n,16)` unit array and `base.logpdf` must accept an `(n,13)` latent array, returning a correctly normalized 13D density. The existing independent X-PSI prior transform must be verified separately. All native source model hashes and identities must be frozen before use. The code does not call source likelihood or implement the original 15D conditional marginalization.

## Commands / tests

`python -m unittest -v` : 8 mathematical tests; includes 13D Jacobian, unit-density identity against a normalized standard normal, finite source-normal CDF bounds for adapted samples, defensive base support, mixture log-density, training-only hashing and reproducibility.

`python synthetic_preflight.py` : **synthetic only**, 2048 training draws plus four disjoint 1024-draw tests with a normalized bounded-Gaussian target, analytic evidence `Z=1`; stores `synthetic_report.json`. It does not call X-PSI and does not use native astrophysical data. The exact target is intentionally easy and cannot establish general performance.

Synthetic observed mean ESS: base 474.16, bounded proposal 655.79 (~38.3% more effective draws). Worst seed max normalized W: base .01185, proposal .00450. Both had zero CDF endpoints at this test size; synthetic evidence error remained within ±0.016 log units. Actual native v1/v2 FAIL statuses remain unchanged.

## Proof and progression gates

1. Verify source-native 13D `base.from_unit` and `base.logpdf` identities, X-PSI 1.2.0 prior normalization, and whether phase-aware mixing is essential. No double-counted radio mass/prior/photons.
2. With the **Windows raw preserved training** records available, fit candidate using training only and freeze version, parameters, model/flow hashes, training SHA and proposal hash **before any held-out read**.
3. Preregister new non-colliding seeds and *unchanged* per-seed gates (ESS≥200/1024, maxW≤.02, min original phase half ESS≥50, half-to-full logI drift≤.10 and across-seed logI range≤.15) before any native likelihood calls. Do not recycle v1/v2 failed held-out data to claim independent improvement.
4. Only after true held-out PASS, expand to the full mass-radius nuisance grid and run physical EOS and rotating-star checks. Until then `full_MR_convergence=NOT_ESTABLISHED`, `EOS_Bayes=NOT_RUN`.

## Files

- `support_aware_mixture.py` — implementation, frozen training-proposal metadata; no photon calls.
- `test_support_aware_mixture.py` — independent unit/synthetic checks.
- `synthetic_preflight.py` — executable zero-photon smoke test.
- `synthetic_report.json` — synthetic test results.

No original v1/v2 source or output was edited. No new native photon calculations were run. In particular, do **not** use the synthetic success to revise any past FAIL or to state the EOS posterior was validated.
