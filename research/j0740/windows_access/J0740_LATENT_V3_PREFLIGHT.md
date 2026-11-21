# J0740 – Latent-space defensive candidate v3 (2026-11-13)

**Status: mathematical candidate / synthetic preflight only. No native X-PSI held-out run, no EOS inference.**

## Why this candidate exists

The verified v2 fixed-point (M=2.000 M☉, R=13.625 km) failed in held-out seeds 198201 and 198211 despite acceptable overall ESS. An independent native post-hoc audit found that broad tail x16 contributed 96 of 99 numeric CDF endpoint events, with roughly 90% of normalized weight coming from the base component. Simply widening tails again is unjustified. There were two conflicting v2 pre-registrations; only the 0.50 / 0.20 / 0.15 / 0.15 recipe ran.

## Candidate definition, exactly normalized

On `z in R^13`:

```
q3(z) = 0.50 N13(z; 0,I) + 0.40 N13(z;mu,Sigma)
      + 0.10 N13(z;mu,1.5*Sigma).
```

Weighted `mu,Sigma` fit ONLY from a new training cohort, with min training ESS 64, 10% identity shrinkage, covariance eigenfloor 0.25. For each evaluation draw, the importance logweight must be `logL(source_transform(Phi(z))) + log N13(z;0,I) - log q3(z)` with correct original X-PSI source prior transport and support normalization. This code does not implement or validate the source likelihood and MUST NOT be mistaken for an EOS result.

Mathematical properties: all Gaussian components normalize exactly; `q3(z) >= 0.5*N13(z;0,I)` everywhere. Direct latent sampling avoids `ndtri` of wrapped phase values; the source's own `Phi(z)` must still be checked for floating point endpoints, and the run must fail closed if any occur. NO sampling clipping, dropping, or reuse of v1/v2 held-out draws.

## Independent checks

- `python -m unittest -v`: 6 tests PASS, including independent SciPy Gaussian-density oracle, fixed-seed 200,000-draw source-CDF endpoint stress, training-only deterministic fit, positive Gaussian defensive floor, malformed-input rejection, and independent synthetic shifted-Gaussian held-out ESS improvement.
- Recorded test-driven endpoint regression: the original Student-t candidate produced 102/200,000 numeric source-CDF endpoint rows (FAIL). It was replaced **before** any native experiment by a modest Gaussian tail; identical regression re-run PASS (0/200,000 for that synthetic seed/config). This is NOT a universal bound; source endpoints must be checked on each real run.
- No new photon/likelihood calls, production data changes, or EOS Bayes calculation were performed.

## Required science gates before using native data

1. Explicitly choose a *new* unique v3 protocol and training/held-out seed split, register candidate code hash and parameters BEFORE any held-out native evaluation. Check seed collision and chronology. Do not use v1/v2 held-out arrays for training.
2. Verify original source transport, exact `pi_eff(M,R)` prior handling, no duplicated radio mass or photon likelihood, fixed support normalization and X-PSI version/source code hashes. The candidate here changes only nuisance proposal `q(z)`.
3. Run independent native held-out pointwise diagnostic, with thresholds frozen in advance (ESS>=200/1024, maxW<=0.02, phase ESS>=50, logI half-to-full drift<=0.10, across-seed logI range<=0.15); preserve all draws/weights, audit CDF endpoints, call counts, hashes and source identity.
4. Only if pointwise diagnostics pass, proceed to grid convergence, rotating EOS physics, and real Bayes posterior. `EOS_Bayes=NOT_RUN`, `full_MR_convergence=NOT_ESTABLISHED` until then.

## Provenance

- Existing source: GitHub `aydinefe2025-svg/Benim-AI-asistan-m`, issue #280, and Notion canonical A01.01.50.
- v2 manifest SHA-256: `9c10db7497aa9216528b7bc47bb9c27c0bb4a2304f5a13808612750b50d26b32`.
- This candidate's SHA-256 files and synthetic results appear in `synthetic_preflight_v3.json`.
