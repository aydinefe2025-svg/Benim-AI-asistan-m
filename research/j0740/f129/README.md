# F129 — Native RNS baryonic mass for two already-certified **numerical** fixed-J roots

Objective: measure RNS `star.Mass_0/MSUN` for the two genuine F128 601×1201, inner 1e−9, fixed-J C stars on the separately **derived** F99 cold causal EOS. Earlier runs emitted mass, radius, spin and J but silently omitted the already-computed `Mass_0` from the output line. An output-only patch enables a sixth numeric column; EOS, equilibrium solver, quadrature, angular-momentum roots and density targets remain unchanged. Every result is checked against original SHA-pinned F128 model outputs.

- Immutable original F128 ultra-tight 601×1201 GitHub artifact ID `14809246981` SHA256 `0302770626ff730657208226e2923a5ed655e8ae39e1235580f67e9180cf9f77`.
- Pinned upstream RNS commit `97e85d325a33e37f702306414533f6cd77812477`; RNS internal radius iteration tolerance `1e-9`, `a_check=0`.
- Distinct, derived F99 source EOS SHA256 `c99eadee07bf6cbbf78f59b6171ef7e21ffad7d034f4ca4e9b7d85d36d9b4331`.
- Two source-verified density points `2622286757812500` and `2622286761718750` g/cm³, target `J=4.8245626795750385e48` in CGS. Uses the **actual prior accepted exact CLI r_ratio** at each density to avoid unnecessarily searching roots again. Verifies native gravitational mass, radius and spin reproduce source published witness before accepting newly emitted native `Mass_0`.
- Both measured `M_0` values and their finite difference reported with gravitational mass delta. F129 is neither a global fixed-J turning-point proof nor a continuous dynamical instability nor a GR virial error bound. Absolute baryon-density calibration of F99 and original-seven EOS physical validity are **not** independently certified. Native Gamma photon nuisance likelihood/prior and final physical 7-EOS Bayes remain **NOT_COMPUTED**.
- If source output changed, C failed, observed J mismatch, inner tolerance violated, or the reference ZIP fails CRC/SHA, F129 rejects and preserves the raw failure.

Run fast unit tests: `python -m unittest discover -s research/j0740/f129 -p 'test_f129*.py' -v`.

Native C computations are run by the GitHub Actions workflow, **not** by unit tests. A passing unit test does not imply that two stars were run.