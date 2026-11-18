# PSR J0740+6620 — F51 SHA-pinned extended mass-domain audit

F51 reuses **already genuinely solved** C/GR RNS stars from F46 and F48 and computes 42 new observation-derived conditional likelihood integrals on the **shared, extended mass window 1.89–2.10 M☉** (24 direct mass-spin solutions per EOS, 168 actual C/GR stars). The 7 source tables are explicitly NEW F42 causal-lift+cold-gas hypotheses, *not* physical confirmations of seven original nuclear EOS theories.

Sources: authentic F38 Salmi 2024 source-prior-corrected six KDE 2D likelihood surfaces; F44 source table hash ancestry; 7 genuine F46 source-C GR result artifacts; F48 genuine recovered WFF1 2.0175 M☉ root; immutable F49 22-node reference result. Each archived source SHA-256 and ZIP CRC is locked in the script, and every star is checked for the observed 346.536369 Hz spin and mass residual. No star is interpolated. Only **integration diagnostic** optionally interpolates the *radius curve between actual solved stellar masses* for quadrature sensitivity; this is NOT a newly solved star.

Why: the old common interval [1.95,2.10] M☉ captures 57.0829% of the truncated radio mass prior. Reuse of already-solved [1.89,1.92] real RNS models extends this to 59.7887%. Separately: the 6 non-WFF1 candidate models have successful exploratory roots above 2.10 (APR4 to 2.15, other 5 to 2.175), but WFF1 has no trusted direct roots above 2.10. We report source-prior contributions across each EOS's *own* measured mass support separately; **scores on different supports must not be ranked as EOS Bayes evidence**.

On six same-photon NICER/XMM KDE surfaces, the narrow bandwidth rank switches from F49 MPA1 to ENG after extending low mass support; medium/wide surfaces remain MPA1-first. This is sensitivity to actual support and KDE and refutes a robust model winner. F49 42 old integrals are reproduced with exactly zero difference.

Stop condition: EOS nuclear microphysics/prior acceptance, global fixed-J stability, and native photon-level X-PSI still NOT_ESTABLISHED/NOT_RUN. 40.2113% of full radio prior remains outside the *common* numerically computed [1.89,2.10] window. No physically justified seven EOS posterior or discovery claim.

Run from repo root after downloading pinned inputs into `$OUT/raw`:

```bash
python -m unittest discover -s research/j0740/f51 -p 'test_f51_*.py' -v
python research/j0740/f51/f51_extended_support_audit.py --f38 $OUT/F38.zip --f44 $OUT/F44.zip --f48 $OUT/F48.zip --f49 research/j0740/f49/F49_7EOS_all_22_real_direct_RNS_integrals.json --curves-dir $OUT/raw --out $OUT/F51_results.json
python research/j0740/f51/f51_numerical_stress.py --f38 $OUT/F38.zip --f44 $OUT/F44.zip --f48 $OUT/F48.zip --curves-dir $OUT/raw --out $OUT/F51_numerical_stress.json
```
