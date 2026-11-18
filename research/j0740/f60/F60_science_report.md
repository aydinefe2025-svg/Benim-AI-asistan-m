# A01.01.51 — F60: two-sided radio-prior tail resolved; physical next-run target

**2026-11-18 | pinned F51 mathematical reanalysis, no newly simulated stars or photon likelihood.**

## New numerical identification

F58 treated 40.21131677% of the radio mass prior outside the seven-way common [1.89,2.10] M_sun interval as unknown. F59 used pre-existing matched F51 ENG/MPA1 F42-causal-lift integrals to extend this pair to [1.89,2.175] M_sun and reduce the pairwise outside prior mass to 9.60891578%.

**F60 independently separates this still-open prior probability by side** using the source-normalized N(2.082,0.0703²) truncated ±5σ prior and the original exact F51 source SHA-256 `3c3584905190012ee61f4b7fee343e3d1c9e28300f9d681e8bf34dd157b5d67d`:

| Uncovered mass range | Prior weight | Percentage |
| --- | ---: | ---: |
| M < 1.89 M_sun | 0.00315538098055 | 0.315538% |
| M > 2.175 M_sun | 0.09293377677444 | 9.293378% |
| Total outside pairwise window | 0.09608915775499 | 9.608916% |

**96.71619457% of that remaining pairwise prior mass is above 2.175 M_sun**. The prioritized mass region for future actual ENG/MPA1 physical-star calculations is therefore the high-mass side, but the lower region's *likelihood* cannot simply be neglected because its prior mass is small. No upper bound for either omitted likelihood is established.

## Hypothetical physical branch continuation targets, NOT EXISTING GR RESULTS

If stable real star solutions and the **same model/prior/likelihood definition** could be continued to these upper masses (this is *not proved*), the Gaussian prior fraction inside [1.89,target] would be:

| Upper mass target (M_sun) | Prior coverage within 1.89–target | Still uncovered outside both ends |
| --- | ---: | ---: |
| 2.200 | 95.022213% | 4.977787% |
| 2.225 | 97.587612% | 2.412388% |
| 2.250 | 98.841517% | 1.158483% |
| 2.275 | 99.382283% | 0.617717% |
| 2.300 | 99.588055% | 0.411945% |

These figures are **probability-mass geometry only**. They neither establish stellar solutions nor justify extrapolating a known unstable EOS branch. One physically admissible EOS may terminate before a suggested target. Then the correct procedure assigns zero likelihood to nonexistent stable solutions only **after** establishing this EOS-specific branch termination; it does not fabricate solutions or renormalize away the missing prior.

For the six F59 matched ENG/MPA1 KDEs, under the **extra hypothetical assumption that the two models have equal average likelihood contribution in the low tail**, the missing high-tail difference T_ENG−T_MPA1 required to reverse the known MPA1 advantage varies between **4.727353 and 5.559659**. Without that low-tail equality this is **not an unconditional reversal bound**. Actual source-native photon likelihood and physical stability are not measured here.

## Scientific acceptance

- F60 genuinely adds a *two-sided* source-normalized prior-tail budget, rather than producing another arbitrary bounded-tail scenario.
- Six locked KDE / matched ENG–MPA1 source-integral comparisons; source-mass validation and new closed-form thresholds are fail-closed.
- Not an original seven nuclear EOS Bayes factor: F42 causal-lift candidates, WFF1 and APR4 differ in mass support.
- Next required *new physical* evidence: source-native pressure-energy and baryon-rest-mass EOS admissibility; real RNS constant-spin and constant-J branch continuation where physically possible; source-native X-PSI nuisance-marginal photon likelihood without reusing Salmi/Huang photons as independent; then seven physically consistent EOS evidences and sensitivity/ESS.
- Existing 12.9 GB Salmi archive and earlier verified source files are not downloaded or rescanned.

**Code:** `research/j0740/f60/f60_two_sided_tail.py`. **Tests:** `research/j0740/f60/test_f60_two_sided_tail.py`. **Output:** `results/F60/F60_two_sided_prior_tail.json`.
