# F95 — Real CompOSE APR(APR) unified EOS 328: static GR radial eigenmodes

**Status:** real published data, numerically solved; **nonrotating** radial dynamical test only. This is **not** the 346.536369 Hz rotating C/RNS star, seven-EOS Bayesian evidence, or full axisymmetric dynamical stability.

## Provenance and preserved source physics

Publisher: CompOSE EOS 328 / Zenodo DOI 10.5281/zenodo.15045814, CC BY 4.0. Original archive (250,015 bytes) verified to MD5 `ccc2fbef2b0f51df389ff8f7d9b00608` and SHA-256 `8338af81270a87c93f19c28df86fbaac5618296aff6535177eb41052c77dcb12` and ZIP members `eos.nb`, `eos.thermo`, `eos.mr` matched byte-for-byte. 1,833 published baryon-number and thermodynamic grid points. This source is **not** APR4_EPP.

The original high-density table contains **24 published nodes** with sound-speed squared > 1. First occurs at `P=448.8893808253 MeV/fm³` (`n_B≈0.87999761 fm⁻³`). Those rows were not altered or called physical.

## Genuine static equilibrium and pulsation computation

Self-contained Python `f95_static_radial_modes.py` integrates the Tolman–Oppenheimer–Volkoff equations in physical geometrized units (km), with the same explicitly disclosed log-PCHIP `eps(P)` numerical interpolation used in the previously published F87 source reproduction. It finds the static `M=2.073 M_sun` star with central `P_c=419.1939452451 MeV/fm³`, radius `10.722365947 km`, and central pressure below the native superluminal threshold. The **interpolated** maximum dP/dε on [source surface, central P] is `0.9838483 c²`; the original published native source values in that interior are also subluminal.

The **general-relativistic nonrotating adiabatic radial Sturm–Liouville** eigenvalue problem (using the source-native barotropic Γ=(ε+P)/P·dP/dε) is discretized using a two-point Gaussian finite-element Galerkin method. Regular center ζ=0, natural free surface; background metric ν matched to Schwarzschild at surface. The four smallest eigenmodes are real and positive, with node counts `[0,1,2,3]`. The fundamental squared angular eigenfrequency on 960 elements is **0.0023674153345452295 km⁻²**, giving the **static fundamental radial frequency 2321.550112788 Hz**.

| Independent mesh N | Fundamental frequency (Hz) | Fundamental ω² (km⁻²) |
|--:|--:|--:|
| 320 | 2321.81822083 | 0.002367962175836 |
| 640 | 2321.61450926 | 0.002367546673788 |
| 960 | 2321.55011279 | 0.002367415334545 |

The 320→960 variation is 0.01155%; tighter background TOV tolerance alters the 640-element frequency by only ~0.0007 Hz (though the surface-radius integration shifts ~0.052 m). **Nine source-locked real-data regression tests pass**, including an independent new 440-element solve at a tighter TOV tolerance.

**Numerical cross-check only, not physical EOS:** The PCHIP TOV mass peak appears around `Pc=1079.936 MeV/fm³`; the fundamental radial zero crossing around `Pc=1079.921 MeV/fm³` at N650. This agreement is a good mathematical consistency check of the discretized radial pulsation equations. **It lies beyond the source's first acausal pressure of 448.889 MeV/fm³ and must not be used as a physically admissible maximum-mass or stability assertion**.

## Strict interpretation and remaining physical gaps

1. Positive ω₀² demonstrates radial dynamical stability **for the modeled static star**, subject to source interpolation, pressure-floor and adiabatic barotropic assumptions.
2. The actual PSR J0740+6620 is rotating at 346.536369 Hz; its nonradial/axisymmetric rotating perturbations **were not solved** here, and spinning-star stability remains unresolved.
3. Source global high-density acausality remains present and any model comparison over its acausal range is not legitimate.
4. No new source photon likelihood calls were performed; neither the old 323 rotating GR stars nor the 42 F38 observational integrals nor the 12.9 GB NICER/XMM archive were repeated. Seven-EOS full-M-R photon-native Bayes model comparison **not done**.

## Method reference

Chandrasekhar relativistic radial perturbation theory / Sturm–Liouville formulation: [MNRAS 502, 1557 (2021)](https://academic.oup.com/mnras/article/502/2/1557/6081082), section 3 equations 7–15; and the source's CompOSE Zenodo [15045814](https://zenodo.org/records/15045814).