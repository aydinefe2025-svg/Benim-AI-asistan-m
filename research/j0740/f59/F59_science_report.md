# A01.01.51 — PSR J0740+6620 F59: matched high-mass ENG/MPA1 audit

18 November 2026. This is a **source-locked reanalysis** of F51, NOT a new C/GR run, original nuclear EOS comparison, photon fit, posterior, or discovery. All values refer to the new F42 causal-lift candidates.

## Important previously unused genuine computations

F51 has directly computed exploratory rotating-star points for both ENG and MPA1 at 2.125, 2.150 and 2.175 M_sun. Both share exactly the extended mass integration interval **1.89–2.175 M_sun**, which covers a radio-prior mass fraction **0.903910842245011**. By contrast, the old seven-way intersection to 2.10 covers **0.597886832314311**, with **0.306024009930700** in 2.10–2.175 now available for the ENG/MPA1 pair. This is NOT seven-way coverage: APR4_EPP reaches 2.15, WFF1 only 2.10.

The F51 source-pinned likelihood-integral entries on the matched 1.89–2.175 interval favor **MPA1 over ENG in all 6 of 6 KDE surfaces**. The original 1.89–2.10 interval favored ENG in two surfaces and MPA1 in four. This newly calculated pairwise audit finds two leader reversals; the increased mass interval changes the ranking decisively *within this specific conditional numerical setup*.

| F51 KDE | Full-prior contribution ENG (to 2.175) | MPA1 (to 2.175) | MPA1 − ENG | Minimum uncomputed-tail mean ENG−MPA1 to reverse |
| --- | ---: | ---: | ---: | ---: |
| Resampled 0.015/0.20 | 1.734549 | 2.251229 | 0.516680 | 5.377091 |
| Resampled 0.025/0.35 | 1.674928 | 2.164930 | 0.490003 | 5.099459 |
| Resampled 0.040/0.50 | 1.575927 | 2.016439 | 0.440511 | 4.584401 |
| Weighted 0.015/0.20 | 1.736838 | 2.248743 | 0.511905 | 5.327392 |
| Weighted 0.025/0.35 | 1.675759 | 2.163369 | 0.487611 | 5.074567 |
| Weighted 0.040/0.50 | 1.576339 | 2.015670 | 0.439331 | 4.572116 |

The last column follows Δtail > (S_MPA1^known−S_ENG^known) / q, where q = **0.09608915775498905** is prior mass **outside both ends** of 1.89–2.175, not only above 2.175. It is a threshold under a *hypothetical, common model-independent mass-prior decomposition*; **no bound on actual tail means has been established**.

Prior mass accounting: [1.89,2.10] = 0.597886832314311; [2.10,2.15] = 0.232256706056625; [2.15,2.175] = 0.073767303874075; outside [1.89,2.175] = 0.096089157754989.

## Scientific limits

- F51 source 168 genuine C/GR stars; all six KDE rows are **pre-existing exploratory integrals**; no newly evaluated models.
- Not all seven F42 candidates have physical branches continued to 2.175; common-seven EOS ranking is invalid on the pairwise window.
- Neither EOS-specific turning-point/fixed-J stability nor original nuclear EOS microphysics, full native X-PSI photon likelihood, prior consistency or final model evidences are established.
- F51 integral numerical resolution (Simpson vs trapezoid) and F42 model causal lifts still need independent evaluation before physical claims.
- The 2026 shifted-dipole and Salmi 2024 analyses share NICER/XMM photons and cannot simply be multiplied.

## Reproduction and provenance

Locked original source `research/j0740/f51/F51_results.json`: SHA-256 `3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d`. Script `research/j0740/f59/f59_matched_pair_extended_support.py`. Checks `test_f59_matched_pair.py`; CI report artifact `results/F59/F59_matched_pair_extended_support.json`.

Next physical result: establish source-native EOS admissibility/stability for these masses, then extend original nuclear EOS (not F42 lifts) and integrate calibrated full source photon likelihood with no radio-prior double count. Until then F59 is a paired diagnostic, **not an EOS Bayes factor**.
