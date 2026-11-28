# PSR J0740+6620 — v3 candidate common-target comparison (2026-11-14)

**Scope:** purely mathematical / synthetic evaluation, with **zero** native X-PSI photon likelihood calls. No source-prior, J0740 data, old experiments, or EOS calculation were changed. This comparison is **not** a held-out PSR J0740 result, not an EOS Bayes posterior, and not evidence of full M–R convergence.

## Why compare

The project already contained *two* independently created v3 proposals on the **same existing PR #317**. The first, `support_aware_v3`, uses a full-support existing/native proposal as its defensive component, plus a change-of-variables-bounded Gaussian. The second, `defensive_latent_v3`, uses a `0.50 N(0,I) + 0.40 N(mu,Sigma) + 0.10 N(mu,1.5 Sigma)` mixture directly in 13D latent coordinates. Their earlier synthetic results were not comparable: different targets, seeds, budgets, and bases. This comparison uses the **same** held-out synthetic targets and samples-per-seed.

## Transparent protocol

- Input source is the **already archived** two mathematical candidates. This comparison adds **no** source-model/likelihood code and does not train with the old v1/v2 J0740 held-outs.
- Reference base for fair mathematical comparison: `N_13(0,I)`. That is **not** a claim that the original native `TransportProposal` base from J0740 is identical to `N_13(0,I)`.
- Targets, all analytic probability densities integrating to 1: (a) normal with mean components (1.2,-0.8); (b) a correlated 13D normal with covariances 0.87 and -0.78; (c) a two-mode mixture in z-coordinate indices 2 and 4 (the `bimodal-phase` label does **not** imply actual circular X-PSI modes); and (d) diffuse normal covariance 1.3 I.
- For **each** target, training uses 4096 scrambled Sobol draws from the same `N(0,I)` base; weighted log-density `logp-logqbase`, retained in full, with distinct fixed training seed computed from target label. No target-specific tuning of fitted mixture fractions, bounds, variance floors, or diagnostics.
- Validation: four fixed scrambled Sobol seeds `40021,40023,40027,40031`, **1024 test draws per seed per method**, independent of training. Every method receives the same 17D Sobol unit coordinates (although mixture allocation differs by each existing mixture's fixed fractions). The latent-v3 direct Gaussian mixture uses its fixed component selection and inverse Gaussian CDF, consistent with its published `.sample()` distribution. All evaluated weights and rows are retained.
- Metrics: ESS = `(sum exp(logw))^2 / sum exp(2*logw)`, max normalized weight, log-evidence estimate `logmeanexp(logw)` with analytical reference `log Z=0`, and number of normal-CDF endpoints in generated latent coordinates. Each summary aggregates *all four seeds*. Output includes per-seed raw metrics.
- No new pass/fail gate for the actual NICER/XMM experiment is created. The historical fixed-point gates are **unchanged**.

## Results (mean ESS out of 1024 / worst observed weight)

| Target | Reference base ESS | Bounded v3 ESS | Direct latent v3 ESS | Reference worst maxW | Bounded worst maxW | Direct latent worst maxW |
|---|---:|---:|---:|---:|---:|---:|
| shifted | 152.73 | 498.52 | **703.69** | 0.08282 | 0.00958 | **0.00336** |
| correlated | 83.05 | 290.19 | **481.12** | 0.10650 | 0.04061 | **0.00860** |
| bimodal-phase (z-mixture) | 168.61 | 412.34 | **537.95** | 0.06831 | 0.00729 | **0.00487** |
| diffuse | 545.64 | 834.97 | **945.05** | 0.02260 | 0.00611 | **0.00187** |

Every method had **zero normal-CDF endpoints** across the 4×1024 draws per target in this controlled experiment. These results neither prove that endpoints cannot happen at larger budgets nor that real source transports behave the same. Max absolute synthetic logZ errors were below 0.107 for reference base, 0.041 for bounded v3 and 0.016 for direct latent v3; inspect the full JSON for each target and seed.

## Verified execution

`python -m unittest -v test_support_aware_mixture.py` in archived bounded source: **8/8 PASS**. `python -m unittest -v test_defensive_latent_v3.py` in archived direct latent source: **6/6 PASS**. `OPENBLAS_NUM_THREADS=1 python compare_candidates.py` executed once, then from a separate directory with symlinks to **unchanged** candidate source: **bit-identical** JSON report with SHA256 `f996404929e8efb4d62537b22b309dc476724d6e1232756207560366690e26c3`.

## Decision / Next real physics gate

Under these four **predefined synthetic** targets, **direct latent v3 is the stronger candidate to preflight first**. This is not permission to launch or claim any real native X-PSI validation. The native source-posterior is unknown and its base is not the synthetic standard normal reference. The comparison *does not* establish phase-torus multimodal coverage, source-prior weight correctness, physical support, full M–R convergence or EOS Bayes.

When Windows SentinelX reconnects, inspect and hash the original native X-PSI `TransportProposal`, source prior inverse transform, and likelihood. Run a zero-photon **real training-only** base-identity and candidate-fit check using only preexisting **training** records; do not use prior held-out v1/v2 arrays in the fit. Document all physical/source support checks. Only then preregister a **single, non-conflicting** new native train/held-out seed split and frozen proposal, with all prior fixed-point gates preserved (ESS>=200/1024, maxW<=0.02, both phase-half ESS>=50, first-half→full logI drift<=0.10, four-seed logI range<=0.15). If any condition fails, no PASS claim.

**Current real status:** `full_MR_convergence=NOT_ESTABLISHED`; `EOS_Bayes=NOT_RUN`; original K4/K8, v1, v2 failures unchanged. Windows host was offline during this independent synthetic comparison; no new native photon calls.
