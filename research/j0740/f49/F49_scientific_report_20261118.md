# F49 | PSR J0740+6620: All seven direct C/GR EOS mass curves complete

18 November 2026 | Scientific archive A01.01.51

**Scope:** Seven distinctly named *new* F42 causal-lift/cold-gas first-law candidate equations of state; NOT the original seven nuclear EOS.

## Closed numerical root gap

The original F46 matrix [GitHub run 44286241129](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44286241129) honestly FAILED because the WFF1 source C/GR root at 2.0175 M_sun missed its strict mass tolerance. The failed run remains preserved.
The new independent [F48 full-GR C solver run 44290378892](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44290378892) recovered the actual direct C model using bracketing in central energy density and axis ratio, not an interpolated star:

| Verified RNS physical output | Value |
|---|---:|
| Gravitational mass (M_sun) | 2.01749999998619 |
| Observed spin frequency (Hz) | 346.536370332 |
| Equatorial radius (km) | 10.101642218 |
| Central density (g/cm³) | 1.9122318e+15 |
| Direct RNS solver trials in nested root trace | 94 |

**Result: 7/7 numerical EOS candidates have 22/22 true C/GR stars each on [1.95,2.10] M_sun at 346.536369 Hz.** This is NOT a global fixed-J stability or microphysical EOS validation.

## Final F49 re-integrated source observational likelihood (middle weighted KDE)

| New EOS hypothesis | Conditional L/Z within measured mass interval | vs. MPA1 | Contribution from measured interval to full prior |
|---|---:|---:|---:|
| MPA1 | 2.413655 | 100.000% | 1.377785 |
| ENG | 2.307997 | 95.622% | 1.317472 |
| APR4_EPP | 0.853017 | 35.341% | 0.486927 |
| WFF2 | 0.592499 | 24.548% | 0.338216 |
| MS1B | 0.386393 | 16.009% | 0.220564 |
| MS1 | 0.329342 | 13.645% | 0.187998 |
| WFF1 | 0.061840 | 2.562% | 0.035300 |

Source F38 reconstructed Salmi marginalized NICER/XMM likelihood ratios use three KDE bandwidths and weighted/equal-resampled samples (6 independent surfaces). The original Gaussian radio mass prior N(2.082,0.0703²), truncated ±5σ, is applied ONCE and consistently across all 7 models.
**Radio-mass prior probability in measured [1.95,2.10] M_sun window = 0.5708291254; outside window = 0.4291708746, likelihood UNKNOWN rather than assumed zero.**

## Six independent observational surfaces and before/after numerical audit

| F38 surface | Highest score (conditional) | MPA1/ENG ratio | F48 correction to WFF1 score |
|---|---|---:|---:|
| `posterior_prior_ratio_resampled_0.015_0.20.npz` | MPA1 | 1.004615 | +0.140811% |
| `posterior_prior_ratio_resampled_0.025_0.35.npz` | MPA1 | 1.047095 | +0.117961% |
| `posterior_prior_ratio_resampled_0.040_0.50.npz` | MPA1 | 1.092613 | +0.081783% |
| `posterior_prior_ratio_weighted_0.015_0.20.npz` | MPA1 | 1.002817 | +0.130300% |
| `posterior_prior_ratio_weighted_0.025_0.35.npz` | MPA1 | 1.045779 | +0.117943% |
| `posterior_prior_ratio_weighted_0.040_0.50.npz` | MPA1 | 1.091824 | +0.081715% |

Only WFF1 changed between F47 and F49: +0.0817%–+0.1408% across six independent source likelihood surfaces; all other six model source scores are numerically identical (maximum other-model difference 0.0).
MPA1 is marginally highest on all six reconstructed surfaces *for this set of new artificial model hypotheses* but the narrow KDE gives a near-tie with ENG. Do NOT report a definitive nuclear EOS winner or physical Bayes posterior.

## Scientific exclusions and unresolved scope

- None of the F42 new causal-lift/cold-gas EOS candidate constructions has been proven to correspond to original nuclear many-body models; WFF1/WFF2 differ by up to around 20% in energy density due to imposed causality. Original nuclear EOS theories are NOT observationally excluded by these model scores.
- Twenty-two increasing-mass rotating solutions do not certify global dynamical stability under fixed angular momentum, nor the physical crust join, baryonic mass calibration or EOS family priors.
- The Salmi F38 grids are source-prior-corrected KDE reconstructions of published marginalized samples, not a new compiled native photon-level X-PSI likelihood.
- Remaining radio-mass support outside [1.95,2.10] M_sun is uncomputed and the seven source-model evidences are not globally normalized. No final seven-EOS posterior, Bayes winner or measured core composition is established.

## Immutable provenance

- F38 ZIP SHA256 `4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307`.
- F44 ZIP SHA256 `b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98`.
- F48 ZIP SHA256 `8217dddfa431d33105421b183b876be3b52cad16525c592459e7f90e8b19b786`.
- Original F47 JSON SHA256 `4e8f13eb5e4788dcf6106108e396df52abca0822f3775b08aa5b2821fd92d2ad` remains unchanged.
- This real 7×22 F49 conditional integral JSON SHA256 `4600ffa338606847fd2981583f38c44945c01525dd24e950ca5c90a14ccb04e8`.

**Stage state:** `F49_7x22_DIRECT_FULL_GR_NUMERICAL_CURVES_PASS`; `F49_6x7_CONDITIONAL_SOURCE_LIKELIHOOD_INTEGRALS_PASS`; `FINAL_PHYSICAL_7_NUCLEAR_EOS_BAYES=NOT_RUN`.
