# PSR J0740+6620 | F47 real seven-source conditional GR mass-window likelihood

**Date:** 18 November 2026  |  **Scientific scope:** 7 distinct F42 mathematical causal-lift first-law cold-gas EOS *hypotheses*, not the original 7 nuclear EOSs.

## What was actually calculated

- 7 pinned full-GR RNS C-source mass-radius curves at 346.536369 Hz, with each candidate integrated through the identical mass window **[1.95, 2.10] solar masses**. F46 Actions run `44286241129`, pinned originals F42 and F44.
- Six F38 Salmi 2024 published-posterior / effective-prior marginalized KDE likelihood surfaces, 3 smoothing bandwidths and weighted/equal-resampled variants. All source archives and seven physical input table SHA256s checked.
- Original radio-mass prior Gaussian `N(2.082, 0.0703^2)` with ±5σ truncation is applied **once**, and only over the predeclared common window. The source F38 effective-prior correction was already applied upstream and was not repeated.
- RNS C mass results: six EOS are direct **22/22** measured stars on the common grid; **WFF1 is 21/22**, with the one failed direct C root at **2.0175 M_sun**. No virtual or interpolated neutron-star model was inserted. Simpson mass integration uses the genuine uneven direct-star mass nodes in WFF1 and strictly identical integration endpoints.
- All seven source-evaluated curves are monotone rising in central density on this *sampled* interval; **not a full fixed-J global dynamical-stability or physical microphysics certification**.

**Full radio mass-prior probability in measured common window = 0.5708291254; remaining probability outside = 0.4291708746.**

## Central KDE bandwidth (weighted published-posterior-derived source likelihood)

| New hypothesis source label | Conditional L/Z within common mass window | vs. MPA1 | Full radio-prior integral contribution **only from measured window** |
|:---|---:|---:|---:|
| MPA1 | 2.413655 | 100.000% | 1.377785 |
| ENG | 2.307997 | 95.622% | 1.317472 |
| APR4_EPP | 0.853017 | 35.341% | 0.486927 |
| WFF2 | 0.592499 | 24.548% | 0.338216 |
| MS1B | 0.386393 | 16.009% | 0.220564 |
| MS1 | 0.329342 | 13.645% | 0.187998 |
| WFF1 | 0.061767 | 2.559% | 0.035258 |

These **L/Z** values are source-normalizer-relative and **conditioned** on a limited common mass window; they are not absolute physical EOS evidence or a final posterior. The contribution column excludes outside support, whose likelihood is **unknown**, not zero.

## Six independent surface checks

| F38 surface | Highest conditional model | MPA1/ENG conditional score ratio |
|---|---|---:|
| `posterior_prior_ratio_resampled_0.015_0.20.npz` | MPA1 | 1.004615 |
| `posterior_prior_ratio_resampled_0.025_0.35.npz` | MPA1 | 1.047095 |
| `posterior_prior_ratio_resampled_0.040_0.50.npz` | MPA1 | 1.092613 |
| `posterior_prior_ratio_weighted_0.015_0.20.npz` | MPA1 | 1.002817 |
| `posterior_prior_ratio_weighted_0.025_0.35.npz` | MPA1 | 1.045779 |
| `posterior_prior_ratio_weighted_0.040_0.50.npz` | MPA1 | 1.091824 |

The narrowest KDE bandwidth produces a **near tie** between MPA1 and ENG (ratios only 1.0028–1.0046). Calling a definitive EOS winner would be unsound. Changing the KDE bandwidth makes a material difference.

## Independent numerical sensitivity checks

- Simpson-vs-trapezoid on the actual seven direct C/GR star nodes across six grids: maximum absolute relative difference **0.1114%** (not a rigorous continuum error bound).
- Empirical leave-one-out: remove one *additional* real interior RNS mass node at a time and reintegrate. Worst sensitivity across seven candidate curves × six F38 surfaces: **0.161009%**; dropping specifically 2.0175 M_sun from each of the six otherwise complete curves changes its quadrature at most **0.015126%**. This is **not an absolute error bound** for WFF1’s missing mass root.
- Original F46 matrix result is **FAILURE (not 7/7 clean)** because WFF1 direct 2.0175 root missed strict mass tolerance (last computed `delta_M=-0.00025277 M_sun`, spin residual `+0.00940 Hz`). This failure remains visible and uncorrected; a valid conditional quadrature of the 21 observed direct roots does not make the failed RNS root PASS.

## Physically essential boundaries — do not overclaim

- F42 causal-lift + gas-surface hypotheses use arbitrary continuation and (for WFF1/2) approximately 20% E changes; they are not the original JESTER nuclear EOS hypotheses, so their relative scores cannot be used to exclude the original WFF or crown MPA1 nuclear microphysics.
- Fixed-frequency monotone finite mass sequences do **not** guarantee full secular/dynamical stability under constant angular momentum. First-law and baryonic mass calibration plus astrophysically justified crust matching remain open.
- F38 is a posterior/prior reconstruction from published NICER/XMM marginalized samples, not a freshly compiled photon-level X-PSI run. The radii are equatorial rotating RNS radii; interpreting the Salmi inferred radius requires a matched waveform-model definition and nuisance treatment.
- The source radio-mass prior has **42.92%** probability outside this common window, and these terms are not known. A valid global model evidence integrates over the full stable-supported mass range with a physically justified family prior, and tests KDE bandwidth, NICER source-prior assumptions, causal repairs and nuisance systematics.
- The output includes mathematically normalized **hypothetical equal-prior weights** only as an illustrative within-window diagnostic; do not call them EOS posterior probabilities.

## Reproducibility / audit trail

- F46 source PR: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/590 ; actual seven-job Actions run: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44286241129 (one WFF1 job FAILED).
- F47 scoring code: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/591 ; local numerical unit tests **16/16 PASS**; real F38+F44 SHA-locked source input and all seven F46 direct-source-output arrays processed locally.
- Source ZIP F38 SHA256 `4bb3220988cb0ecd5cb1ef17370721d3fec82f99dc48f7ca57217cce3dc2d307`, F44 ZIP SHA256 `b45d99bf5d58179f49df12a5101b8c40204e146aef31e0987b5260d6ffd0bd98`. Per-model seven F46 JSON file SHA256s are in the machine result.
- `F47_real_seven_common_window_integrals_20261118.json`, `F47_direct_mass_node_omission_sensitivity.json`, `F47_real_seven_source_conditional_likelihood_20261118.csv`, this report, sources, tests and SHA manifest packaged as local derived scientific work; original source EOS and previous F31-F46 archived work unchanged.

**Stage status: `F47_REAL_CONDITIONAL_COMMON_WINDOW_INTEGRAL=COMPUTED`, `F46_WFF1_MISSING_DIRECT_ROOT=OPEN`, `FINAL_SEVEN_PHYSICAL_EOS_BAYES=NOT_ESTABLISHED`.**


## F48 direct-root rescue and F47 re-integration — 18 November 2026

This section supersedes the older sampled-grid gap and score values above for the **post-F48 common-window calculation only**. It does not supersede the recorded failed F46 run.

- F48 real direct RNS C nested root for WFF1 at 2.0175 M☉ and 346.536369 Hz used 94 actual solver models; no stellar model was interpolated. Measured mass 2.0174999999861853 M☉, R_eq 10.101642217945683 km, central energy density 1.9122318463178555×10^15 g/cm³, spin 346.5363703320838 Hz; residuals −1.38147×10^−11 M☉ and +1.33208×10^−6 Hz. F48 Actions run [44290378892](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44290378892) SUCCESS; artifact 14421121729 SHA256 `8217dddfa431d33105421b183b876be3b52cad16525c592459e7f90e8b19b786`. Original F46 failed artifact remains retained by SHA256 `bc4795ab244cc169f5ee5011c3ba1ac4646926a14c982b94d07808d647a955f3`.
- F47 Actions run [44306741205](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/44306741205) SUCCESS re-ran 18 unit/fail-closed tests, verified the immutable F48/F38/F44 inputs, and integrated the seven 22-node direct C/GR curves against all six F38 likelihood surfaces. Raw result is in artifact 14428273094, ZIP SHA256 `8c1706269fdae407562f60f5015749204c78bb8dac51a51bf917f2abf21edd32`. The 42 logged scores and gates are also in `F47_F48_postroot_conditional_score_summary_20261118.json` (scores rounded to 12 decimal places).

Central weighted KDE conditional common-window scores after the F48 root are: MPA1 2.413655036291, ENG 2.307996890446, APR4_EPP 0.853017186096, WFF2 0.592499085413, MS1B 0.386392503489, MS1 0.329342084015, WFF1 0.061839814696. MPA1 ranks first on all six surfaces. At the narrowest weighted bandwidth MPA1/ENG = 1.002817227, still a near tie. The common window contains 0.5708291254 of the radio prior; the remaining 0.4291708746 has unknown likelihood and was not set to zero. These are source-normalizer-relative conditional window scores, not Bayes factors or EOS posterior probabilities.

**Open gates:** the seven models are F42 artificial causal-lift/cold-gas hypotheses, not validated original nuclear EOS. Physical microphysics acceptance and global fixed-J stability remain `NOT_ESTABLISHED`; native photon-level X-PSI fit, source-native prior/nuisance reanalysis, and the full physical seven-EOS Bayes posterior remain `NOT_RUN`. The original F46 CI failure is preserved even though the missing sampled WFF1 direct root is now recovered.
