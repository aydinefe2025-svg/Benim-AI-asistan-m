# F139 · Original seven EOS native low-pressure seam experiment

Input: **seven unchanged JESTER source NPZ**, upstream git `e6768650ce992abfd1153a6833857572fe5cd230`, native LALSuite pinned `7.26.16`.

Hypothesis: six nuclear EOS files have nearly identical `cs2<0` at input pressure index 254; determine if source-native derivative is negative **between nodes** (a genuine LAL interpolant issue) and whether this is a shared crust seam. APR4_EPP is a matched negative control.

At each model, sample six pressure intervals surrounding index 254 with 65 log-pressure points per interval (385 native E(P), E'(P) pairs per EOS). Retain all 2,695 native evaluations, source SHA, pressure/energy and all c_s² values, sign-change brackets (not physical boundary certainties). Source numerical anomaly is NOT an assertion that a microscopic nuclear EOS is invalid, or that a stable star or X-PSI Bayes posterior has been computed. In particular F79's P/E/H necessary-condition failures are **not** automatically fixed by the F132 native n correction.

Test-first: captured baseline missing-module red; six positive and negative-source regression tests green. Native acceptance requires actual GitHub Actions SUCCESS and independent artifact audit. Original F134–F138 APR4 science was already completed; F139 is an independent shared-crust diagnosis, not a rerun or downgrade.