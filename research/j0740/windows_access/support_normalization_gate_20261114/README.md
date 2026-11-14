# J0740 — Source-prior support normalization: fail-closed mathematical preflight

Date: 2026-11-14. **NOT a new NICER likelihood calculation, not a measured π_eff(M,R), not an EOS posterior.**

## Why this gate exists

A source-likelihood integral over a physically allowed region A is ambiguous until we know which probability measure the historical source prior actually uses:

- **Unconditioned proposal with support indicator:** `Z_raw = ∫ p0(x) 1_A(x) L(x) dx`. The evidence under the **conditional prior on A** is `Z_A = Z_raw/S`, where `S = ∫ p0(x) 1_A(x) dx`.
- **Source transport already samples the conditional prior:** `Z_native = ∫ p0(x | A) L(x) dx` and **no further division by S is permitted**.

Thus in log space, `logZ_A = logZ_raw - log(S)` **only in the first case**. Applying it twice or skipping it when required changes the absolute Bayes evidence without improving proposal ESS. It does not, by itself, alter normalized weights within one fixed model. No numerical posterior may be approved until source runner/prior/config explicitly determines the case.

The historical study mentions a source-support factor `0.24947354926879406`, but **this tool has not authenticated its source-run identity, measure, precision, or uncertainty**. Never automatically apply that number. This preflight demonstrates the algebra, not a source posterior correction. Source native evidence may also have another built-in normalization; verify it before integrating.

## Implementation and safety

`support_normalization_gate.py` implements an explicit branch between `unconditioned_support_indicator` and `already_conditional`. An unknown measure fails closed. An already-conditional prior combined with a support factor fails closed (double-count prevention). Unconditioned correction requires an explicit positive support probability and human-readable provenance label; **labels are not cryptographic verification** and outputs are always marked `MATHEMATICAL_ONLY_SOURCE_NOT_VERIFIED`. Raw and corrected numbers are both returned, not silently overwritten.

If an actual support probability was estimated from *independent, iid* prior draws as a Bernoulli support fraction, optional `(successes,total)` yields a 95% Wilson interval and corresponding bounds on conditional log evidence. These bounds **ignore uncertainty in the numerator Monte Carlo estimate** and cannot be used for weighted, correlated or deterministic quasi-MC support samples. Zero successes or unsupported measurement models fail closed. No arbitrary clipping or hidden threshold adjustment.

## Measured tests

- Recorded RED: 8 test methods errored with `NotImplementedError` while the production implementation was a deliberate stub.
- GREEN: `python -m unittest test_support_normalization_gate.py -v`: **8 tests, 0 failures, 0 errors**; `python -m compileall -q .`: exit 0.
- Analytic controlled quarter-support example: 4096 deterministic equal-mass grid entries, 1024 accepted; raw log evidence = log(0.25) = -1.3862943611198906, corrected log evidence = 0. This deterministic example is an exact algebra check, **not an iid uncertainty estimator**.
- `support_counts=(25,100)` toy illustration yields a Wilson support interval and corresponding conditional log-evidence interval. It is **not the J0740 support estimate**.

## What remains explicitly unverified

- Whether Salmi's exact source-run conditional prior transport samples an already-conditioned measure or a raw measure with support rejection, and how the 0.2494735 factor was derived.
- Identity of source 13D nuisance parameterization vs headline source posterior, original `X-PSI` 1.2.1 vs current local 1.2.0, and source photon likelihood.
- Nuisance integration at arbitrary M,R, radial 16 km truncation, rotating-star EOS prior/likelihood and posterior; all **NOT_RUN/NOT_ESTABLISHED**.

The Windows host was checked and is still offline at this preflight. Preserve old v1/v2 and K2 FAIL results and all source files. This is a new narrow normalization gate, not a new proposal and not a claimed scientific discovery.
