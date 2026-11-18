# PSR J0740+6620 APR4 physical EOS audit (2026-11-18)

This evidence bundle supersedes earlier partial-status descriptions. The original JESTER APR4_EPP NPZ is preserved byte-for-byte; its SHA-256 is `639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88`.

## Established evidence

- Exact producer: JESTER commit `e6768650ce992abfd1153a6833857572fe5cd230`; pinned LALSuite 7.26.4 wheel SHA-256 `d37698363f9ec74255514ecadc5d8aeb4aca7ad3f04cd50534ac0caffe55f4bf`; native table SHA-256 `2a63cd7f1e1c5a158bb3cc06ab4b51f4344a9a1e6bfaeec7f98937c3d5a5447f`; source C SHA-256 `1c84c672e663d853b1ef87f9bb23520e85ab007c2b4e66048d2abc82bc7825df`.
- All 865 JESTER exported APR4 samples reproduce from the native table's LALSuite natural cubic to relative/absolute errors below 8e-15 for epsilon, dlogepsilon/dlogP and pseudo-enthalpy.
- The native continuous interpolant is thermodynamically monotone (`min dlogepsilon/dlogP=0.3008816956`) but acausal (`max cs2=1.1000105502`); the first cs2=1 crossing is P=7.1581887724e-10 m^-2. Original APR4 is therefore not accepted as a globally physical EOS.
- A separately named causal completion retains the native crust and table to that crossing, uses a first-law Gamma=5/3 low-pressure anchor and cs2=1 high-pressure continuation. The original input is untouched.
- Independent TOV turning point for that explicit completion converges at M=2.16932323 Msun, R=10.03203 km, Pc=1.24638e-9 m^-2. 61-to-121 grid changes: 2.15e-8 Msun and 5.54e-5 km. Stable-branch R at 2.073 Msun is 10.69772 km; an independently reproduced JESTER/LALSuite static point is 10.69863 km (0.00092 km difference).
- Real tests: `test_native_lalsuite_apr4_causal_model.py` validates provenance hashes, source reproduction, continuous causality/stability, first-law shape, TOV convergence and independent source M-R agreement. Recorded result: `APR4_native_LAL_causal_candidate_test_results.json`.

## Explicit unresolved statuses

- Original APR4 physical M_TOV: `NOT_ESTABLISHED` because its native high-pressure EOS is acausal.
- Physical zero-pressure chemical potential / absolute baryon density normalization: `NOT_ESTABLISHED`; two-column native table has no baryon-density or physical mu0 anchor. First-law shape is computed, but the JESTER `m_avg` conversion is not a physical normalization proof.
- New causal EOS RNS rotating-root run: PASS. Direct roots on the separately named completion at M=2.073 M_sun and f=346.536369 Hz are source-locked. The local table SHA 5071ae5c70db9b374275fd2b4f2c6b8cc3365924285cbe84d75e14cf02b0b9c7 gives grid radii 10.78271188 and 10.78085229 km (difference 0.00185959 km). The conditional evidence workflow generated a distinct 200-point table SHA affeeaadb03c578acba17e1992f299850abfbbdee50314268acb93692a7f1d89 and re-solved its anchor on that exact table: M=2.07300000010 M_sun, f=346.53636862 Hz, R_eq=10.78235145 km. Do not mix roots between tables; absolute baryon normalization remains NOT_ESTABLISHED.
- Approximate F38 nuisance-marginal relative-likelihood integration along the reanchored causal-completion RNS curve: `PASS_APPROXIMATE`. With normalized uniform central-energy-density prior on 1.923–2.123 M_sun and radio Gaussian applied once, weighted Z_EOS/Z_F38 values at bandwidths (0.015 M_sun,0.20 km), (0.025 M_sun,0.35 km), (0.040 M_sun,0.50 km) are 2.215913, 2.545479, 2.830869. Published-equal values are 2.213360, 2.544637, 2.829855. Weighted/equal differences are 0.1152%, 0.0331%, 0.0358%; all six coarse/fine changes are below 0.0414%. Bandwidth spread remains about 28%, so this is a conditional approximate result, not an EOS posterior or ranking. Native compiled X-PSI photon reevaluation and final seven-EOS Bayes remain `NOT_RUN`.

Run the test module in a Python environment with NumPy/SciPy: `python -m unittest test_native_lalsuite_apr4_causal_model -v`. The model is an explicitly defined candidate completion, not a claim that APR4 itself is causal or that a final astrophysical EOS posterior is complete.

