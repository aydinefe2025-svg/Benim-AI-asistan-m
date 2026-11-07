# J0740 seven EOS GR model-validation gate

This run independently computes seven EOS (**APR4_EPP, ENG, MPA1, MS1,
MS1B, WFF1, WFF2**) using **the same pinned JESTER thermodynamic sources**
and pinned upstream RNS solver at the actual PSR J0740+6620 spin,
346.536369 Hz. Each EOS is converted explicitly to RNS format and receives
an increasing-central-density scan. A target-mass rotating solution and
*another static RNS solution at the same gravitational mass* are independently
bracketed and solved. The static radius must agree with the original JESTER
TOV radius within 0.25 km.

**Scientific output:** numerical rotating equatorial radius vs. gravitational
mass (sampled density sequence), target-mass model and corresponding
fixed-gravitational-mass static reference. The full source SHA, table hash,
solver hash and intermediate bisection steps are preserved.

**Never claim:** a new astrophysical object or first discovery, empirical
validation of a true nuclear EOS, a universal radius measurement, or final
NICER/XMM likelihood/Bayesian evidence. A single fixed-EOS model may agree
with the Salmi 2024 observational radius but it is not a posterior inference.

**Failure modes:** EOS-specific RNS failures, inability to bracket an
increasing stable sequence, physical mass/radius mismatch or static TOV
disagreement are explicit `NOT_VALIDATED` states. Partial outcomes fail
CI. The old verified MPA1 single model is not overwritten.

**Not run:** the already verified local 12.9-GB NICER archive.
