# PSR J0740+6620 — source-grounded conditional EOS calculation

This directory makes the existing audited **F30** numerical science code available as version-controlled, inspectable Python rather than only in a ZIP and Notion narrative. It is **not** a complete neutron-star EOS inference, an exact NICER/XMM event-level photon likelihood, or a general-relativistic rotating-star solver.

## Reproduce with an already available Salmi 100,000-draw source file

Requirements: Python 3.11+, NumPy and SciPy. No automatic downloads, paid services, or new large archives. The binary source posterior is intentionally excluded.

```bash
python -m pip install numpy scipy
python -m unittest -v test_j0740_science
J0740_POSTERIOR="/existing/path/J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz" python phase30_prior_corrected_eos.py
```

On PowerShell, set `$env:J0740_POSTERIOR = 'C:\path\to\existing\J07406620_amsterdam_gamma_NICERXMM_equal_weights_recent.npz'` and then run `py -3 phase30_prior_corrected_eos.py`. The program **verifies the source NPZ SHA-256** before running.

The script writes `phase30_seven_eos_prior_corrected_proxy.json` in its directory. Existing reference JSON files are included to make old results inspectable; change only through a reproducible code/fixture update. For auditing code without 100k source file, run the tests; no data are silently downloaded.

## Audited source, input identities and scientific boundary

- Salmi et al. (2024) J0740 NICER+XMM posterior samples. Source 100k NPZ SHA-256: `4587a7d71aca7b561e5cf22623e3f0e2d80a6c54add0ecb7abc0389d705e8d5b`.
- X-PSI source `v1.2.1` `Spacetime.py`, Cython effective gravity `effective_gravity_universal.pyx`; original source implementation was separately compiled and compared with F30 Python on 100k original samples. This package includes the independently audited Python translation, not the full native X-PSI runtime.
- Seven EOS curves: JESTER/LALSuite sources, commit `e6768650ce992abfd1153a6833857572fe5cd230`; adaptive interpolation error on relevant mass domain previously verified below 2m.
- Source-native hard polar radius: `R_polar >= 3.01 GM/c^2`. Source radio mass prior: truncated Gaussian `M~N(2.082,0.0703)` truncated to +/-5 sigma.
- Empirical spin correction at 346.536369 Hz is **not** a validated full rotating-GR stellar sequence. Source KDE divided by analytically reconstructed source prior is **only a model-conditional likelihood proxy**.
- The radio timing mass prior is canceled and reapplied once algebraically when source and target radio priors match. A proper EOS mass/central-density population model and observational selection function are still required for the actual joint Bayes evidence.
- Earlier model-conditional Legred 10k GP posterior is separate and must not be multiplied into these scores as independent NICER data.

**Do not normalize the seven numerical proxies into purported EOS model probabilities.** The final science gate requires source-native nuisance-marginalized X-PSI photon likelihood, independently validated rotating-star EOS sequences, selection-normalized mass population and convergence checks. See the single tracking issue [#280](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/280) and canonical Notion record (A01.01.51).
