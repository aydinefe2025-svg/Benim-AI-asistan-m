# PSR J0740+6620 F38 — Published-source marginalized likelihood reconstruction

This is a **new source-posterior-to-likelihood 2-D grid**. Unlike prior F33 normalization and F34/F35 point/curve checks, the exported gridded likelihood can be reused by *future* physically valid EOS branches. No 12.9 GB photon archive is needed to reconstruct the nuisance-marginalized **relative** likelihood **conditional on the source X-PSI prior assumptions**.

Mathematical identity: `posterior(M,R) / source_prior_eff(M,R) = marginalized_likelihood(D|M,R) / evidence_normalizer`. Gaussian-smoothed posterior reconstruction introduces a bandwidth systematic, so these are approximate estimates of an exact statistical identity. Do **not** treat numeric values as a fully source-native compiled X-PSI photon reanalysis, or as physical seven-EOS Bayes model evidence.

- Source: Salmi et al. (2024), Zenodo 10519473, `mr_samples_and_contours.tar.gz`, source SHA256 `1549467c64a8801c39213bd28c89737d087cc5ab7a70da1d8d3a32b2d09185c8`, MD5 `ca8e70eeca81feb71321f1a88a24f2f9`.
- Prior: exact-source port from F33, with source 15D prior marginalized to `(M,R)`, hard physical support and `S_MR=0.5780634948872538`. Includes the radio mass prior; do not count radio data twice.
- Main code: `source_mr_marginal_likelihood.py` (Python ≥3.12, NumPy, SciPy), `f33_prior_source.py`, `test_source_mr_marginal_likelihood.py`.
- Grid: 401×581 (M from 2.082±5×0.0703 M☉, R from 4.42987536 to 16 km), weighted and equal-resampled versions, 3 bandwidths each. The hard source support mask prevents extrapolating outside the source prior.
- Validation: strict data hash and row counts; ∫prior=1, ∫posterior=1, ∫prior×L/Z=1, weighted/equal resample agreement; generated known-likelihood and constant-likelihood synthetic fixtures (5 tests).
- Acceptance: this supports **relative source-marginalized likelihood-surface evaluation**; **not** absolute source evidence or automatically a valid 7-EOS comparison. EOS models still need stable/casual source physical eligibility, population mass priors, and model calibration.

Reproduce: `python -m unittest -v test_source_mr_marginal_likelihood` then `python source_mr_marginal_likelihood.py --source <verified Salmi .tar.gz> --outdir results/F38`.