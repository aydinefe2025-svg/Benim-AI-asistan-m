# PSR J0740+6620 — F51 extended common mass window (18 Nov 2026)

**Executed numeric scope:** 168 existing, source SHA-locked direct C/GR RNS stars (7 newly labeled EOS hypotheses × 24 actual common mass target roots) at f=346.536369 Hz; 42 new F38 published source-prior-corrected KDE integrals; 42/42 F49 previous [1.95,2.10] integral scores independently reproduced with max absolute error 0.

## Full radio-mass prior support
- Previous common support [1.95,2.10] M☉: **57.082913%**.
- New source-pinned common [1.89,2.10] M☉: **59.788683%**.
- Uncomputed outside new common window: **40.211317%**. Never assign this to zero without a defensible EOS prior/stable branch selection.

## New conditional L/Z scores for same 1.89–2.10 M☉ mass prior
| F38 KDE surface | MPA1 | ENG | First | ENG/MPA1 |
|---|---:|---:|---|---:|
| resampled_0.015_0.20 | 2.484119 | 2.531932 | ENG | 1.019248 |
| resampled_0.025_0.35 | 2.422913 | 2.375681 | MPA1 | 0.980506 |
| resampled_0.040_0.50 | 2.291497 | 2.161327 | MPA1 | 0.943194 |
| weighted_0.015_0.20 | 2.483715 | 2.536033 | ENG | 1.021064 |
| weighted_0.025_0.35 | 2.421534 | 2.377364 | MPA1 | 0.981760 |
| weighted_0.040_0.50 | 2.290884 | 2.162334 | MPA1 | 0.943887 |

**New finding:** On the previously restricted [1.95,2.10] M☉ window MPA1 leads all six surfaces. Adding two already direct-RNS-computed lower masses **reverses narrow-band rankings to ENG first (2/6)**; the medium and wide bands remain MPA1-first (4/6). This is a concrete model-prior-support/KDE systematic, not an observational winner.

## Actual high-mass exploratory direct-C stars *outside* the common all-seven comparison
| New model | Upper directly computed RNS mass (M☉) | Prior fraction over its own [1.89, max] mass window |
|---|---:|---:|
| APR4_EPP | 2.150 | 83.014% |
| ENG | 2.175 | 90.391% |
| MPA1 | 2.175 | 90.391% |
| MS1 | 2.175 | 90.391% |
| MS1B | 2.175 | 90.391% |
| WFF1 | 2.100 | 59.789% |
| WFF2 | 2.175 | 90.391% |

These model-dependent upper intervals are **not shared support** and not established stable branches. Their conditional scores cannot be fairly compared or interpreted as EOS posterior ratios. F46 did not find WFF1 actual direct stars above 2.10; these failures are preserved.

## Numerical and scientific acceptance
- 12/12 synthetic + fail-closed unit tests passed, SHA/CRC of all 11 primary science input ZIPs validated, 168 C/GR root residuals checked. F49 exactly reproduced; F51 full results preserved as JSON.
- Dense PCHIP interpolation between **real** stellar roots was used only to stress-test quadrature; it is **not** a direct C/GR star solution. Its maximum relative deviation vs direct-node Simpson was 0.1566%.
- Seven F42 source EOS are **new nonunique causal-lift cold-gas candidate hypotheses**, particularly WFF1/WFF2 energy corrections ~20%; none individually certified as original nuclear EOS.
- **NOT_ESTABLISHED:** physically justified crust/microphysics EOS priors; global fixed-J stability; valid joint photon-level X-PSI likelihood; EOS-dependent full prior support.
- **NOT_RUN:** final physically justified original seven-nuclear-EOS Bayes posterior. Salmi 2024/other shared photons must not be multiplied as independent observations.

GitHub CI reruns source downloads and independent computations; PR may be merged into APR4 research branch only after actual green CI and JSON 42/42 reproducibility.
