# A01.01.51 · PSR J0740+6620 — F58 mass-prior tail: EOS ranking partial identification

**18 November 2026 | original scientific result: rigorous sensitivity bounds, not new stars or EOS Bayes.**

## Data lineage

The source is the original checked-in **F51_results.json** from the completed run with **168 directly computed C/GR stars** and 42 observational overlap integrals, under the seven **new F42 causal-lift cold-gas candidate hypotheses**, not the seven original nuclear EOS. Verified SHA-256 of the source JSON: `3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d`. Parent 2026-11-18 F51 source artifact is `J0740_F51_Expanded_Common_Mass_Support_CGR_Likelihood_20261118.zip` (ZIP SHA-256 `4ceef366e0fdd90886d3f3f526e8a1663f2a2ee1aec4ec31f5bc48a38c398340`). The existing common mass interval is **1.89–2.10 solar masses**. Reusing original F51 means **no re-running of stars, KDE source data, or photons**.

## Actual identification problem

For EOS hypothesis *i*, let *L_i* be F51's observational likelihood / source-effective-prior ratio **conditional on the common mass window**, and *T_i* be the unknown nonnegative, same-unit likelihood ratio **radio-prior averaged outside that window**. The full-radio-prior integral is mathematically

\[ S_i = w L_i + q T_i, \quad w = 0.597886832314311, \quad q = 0.40211316768568905. \]

F51 measured only the first term. *T_i* is **not** observed, computed, or proved to be zero. The equality is a diagnostic decomposition that presumes an otherwise valid EOS-specific stellar branch, consistent source-mass prior, and likelihood definition across the missing region; none of these physical conditions is currently established for all seven F42 candidates.

For each of six actual F51 KDE reconstructions, the two in-window leaders ENG and MPA1 differ only slightly. A competitor could overtake an in-window leader **even if the leader's tail mean were zero**, once the competitor's missing-tail mean exceeds

\[ T_{\mathrm{reverse}} = \frac{w\,(L_{\mathrm{leader}}-L_{\mathrm{runner}})}{q}. \]

| F51 reconstructed KDE | In-window leader | Runner-up | Minimum competitor tail mean to reverse with leader's tail = 0 |
|---|---|---|---:|
| Resampled, bandwidth 0.015 / 0.20 | ENG | MPA1 | 0.071092 |
| Resampled, 0.025 / 0.35 | MPA1 | ENG | 0.070228 |
| Resampled, 0.040 / 0.50 | MPA1 | ENG | 0.193545 |
| Weighted, 0.015 / 0.20 | ENG | MPA1 | 0.077790 |
| Weighted, 0.025 / 0.35 | MPA1 | ENG | 0.065675 |
| Weighted, 0.040 / 0.50 | MPA1 | ENG | 0.191135 |

**Critical distinction:** these are reversal *thresholds under the most favorable hypothetical competitor-tail setting*, **not estimates of the uncomputed tail or actual model probabilities**.

## Explicit bounded-tail sensitivity

If we **hypothetically** impose `0 <= T_i <= B` for *every* candidate independently, the resulting identification interval is `w L_i <= S_i <= w L_i + q B`:

- `B=0.05`: each KDE's current leader is mathematically guaranteed *within the made-up bound*.
- `B=0.10`: ENG and MPA1 are both mathematically possible top models for each *narrow and medium* KDE; the wide-band models still favor MPA1 under this bound.
- `B=0.20`: both ENG and MPA1 are possible leaders across **all six** KDE reconstructions.
- No finite bound on any *T_i* was established from the available F51 source data. Consequently an unbounded nonnegative tail alone makes the full-prior ranking **not identifiable**, even before debating original EOS microphysics.

These assumptions are **not constraints learned from NICER**. Different physical EOS priors, stable branch availability and true source-native photon likelihood might change every value. The 2026 shifted-dipole model shares photons with Salmi 2024; it must not be treated as an independent product likelihood. The F56 native WFF1 source contains measured causal and monotonicity issues, and F42 has a 20.356% energy lift for WFF1: conditional F51 rankings **cannot** be called nuclear-EOS Bayes factors.

## Tests and reproducibility

- Standalone `f58_common_tail_partial_identification.py` reads and SHA-verifies original F51 JSON; checks **all 42** input F51 common-window contributions reconstruct as `w×L`, all seven models, six KDE surfaces, 168 genuine source RNS stars, common interval, original source caveats and nonnegative finite values; never creates new synthetic star evidence.
- Nine fail-closed unit tests: exact algebraic reversal threshold, set-valued bounded winners, negative likelihood, wrong prior, inconsistency between weight and integral, model-specific mass support leakage, EOS/surface missing, source-posterior mislabeling, pinned SHA declaration.
- Independently run Python tests **9/9 pass** on the preexisting source artifact. The output JSON lists each surface, EOS's known score and all hypothetical interval scenarios; detailed CSV contains 6 thresholds.

## Scientific decision / next task

**Result**: We cannot claim ENG or MPA1 is the observationally proven winner, even conditionally across KDE bandwidths. The correct next computation is **physical EOS-admissible global branch continuation / mass-prior coverage and source-native likelihood integration for each independent EOS**, or a defensible upper bound on the omitted likelihood for each model. A lower-effort option is to compute the original F38 effective KDE across its support and derive certified bounded-tail likelihood limits **without reusing same photons twice**, but a KDE numerical maximum cannot validate an unphysical stellar branch.

**NOT_RUN/NOT_ESTABLISHED:** native nuclear EOS priors, physically admissible rotating model branch across full radio-prior support, photon-level joint X-PSI posterior, and final seven-original-EOS Bayes factors. No claims of stable maximum or new observational discovery.