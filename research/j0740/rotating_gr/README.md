# J0740 full-GR rotation solver preflight — NOT final EOS inference

This small, read-only numerical validation is intentionally **independent** of the earlier semi-empirical 2020 spin correction in `research/j0740/rotation_same_baryon_audit.py`.

RNS is the axisymmetric general-relativistic neutron-star solver by Stergioulas and collaborators. RNS code is pinned to commit `97e85d325a33e37f702306414533f6cd77812477` of `rns-alberta/rns` and RNS EOS tables to `7ef71a578d2e52dede24bce055839f2b74f43721` of `rns-alberta/eos`. RNS itself and its EOS are **not vendored** in this repository. The GitHub Actions workflow clones them reproducibly into the temporary CI runner, compiles the upstream C code, runs 300-Hz published control and a **346.536369-Hz real GR stellar model** at fixed central energy density `1e15 g/cm3`, and records source hashes and output JSON. It must reproduce the published control `M≈1.453 M☉`, `Req≈11.48 km` to the cited rounded precision.

**Critical:** the RNS library table `eosAPR` is *not* JESTER's `APR4_EPP`. It is used here only to validate the full GR solver pipeline and quantify a model's static vs 346.536Hz rotation at matched **central density**, not to update the seven-EOS candidate scores or to infer J0740 radius at ~2.073 solar masses. This is **not** a neutron-star EOS posterior, event likelihood or Bayes factor. No 12.9GB dataset is required/downloaded.

The proof is an actual independent RNS C-physics run in GitHub Actions, rather than another test of the earlier Python fit. Once validated, the next science requirement is matched thermodynamic (energy density/pressure/enthalpy/baryon density) JESTER EOS tables and a rotating stellar sequence crossing the observed J0740 gravitational mass; **never** infer APR4_EPP from eosAPR just because the names sound similar.

References: https://github.com/rns-alberta/rns ; https://github.com/rns-alberta/eos ; https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/280.
