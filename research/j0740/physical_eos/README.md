# PSR J0740+6620 APR4_EPP physical EOS audit — partial

This bundle audits the existing JESTER-generated `APR4_EPP.npz` without modifying it. Run `python apr4_firstlaw_n_audit.py` in an environment with NumPy and the NPZ at the path embedded in the script (or adapt only the input path). The script asserts the supplied NPZ SHA-256, checks the source density proxy, reconstructs the first-law density shape, and records causality samples.

## Established

- Source NPZ SHA-256 matches `639c5381d49e13383c553771725f935b292e8ef7ff23367bd399a2bb9a3b7b88`.
- All 865 tabulated source `n` values equal `epsilon/m_avg` exactly within the script check. This is an energy-density proxy, not the first-law absolute baryon density.
- The proxy's log chemical-potential/enthalpy first-law residual reaches 0.6241073.
- First-law shape follows `n(mu0)=(epsilon+P) exp(-h)/mu0`; the physical zero-pressure chemical potential `mu0` is absent because the NPZ begins at `P=1e26 Pa` and carries no low-pressure crust anchor. Absolute crust normalization is therefore NOT_ESTABLISHED.
- First sampled acausal point is index 812 (`cs2=1.02906747`); maximum sampled `cs2=1.09827825` at index 813.

## Not established / not run

- Byte-for-byte comparison of the exact JESTER source NPZ producer and a versioned native LALSuite APR4_EPP table, including high-pressure nodes and SHA: NOT_ESTABLISHED. The upstream native table can be inspected publicly, but the exact source file could not be fetched and hashed in this restricted environment; the NPZ itself does not record the producer version.
- Continuous native LALSuite causality and thermodynamic-stability checks: NOT_RUN.
- Physical crust matching and absolute first-law normalization: NOT_ESTABLISHED.
- Causal replacement EOS, physical static maximum/turning point, and new rotating GR runs for such a changed EOS: NOT_RUN.
- Source-native X-PSI effective prior, nuisance marginalization, and final EOS Bayes factor: NOT_RUN. No photons or radio mass were added or re-counted.

The previously reported conditional turning point lies in the acausal source region and is not a physical `M_TOV`. This bundle does not revise it or claim a physical maximum mass. `NOT_RUN` means no calculation was performed; `NOT_ESTABLISHED` means available evidence does not support the claim.
