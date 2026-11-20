# F86 — Correct F85 original X-PSI native event replay formula

**Real bug:** Historic original X-PSI 198301 logweight audit subtracts a nuisance support factor, `logw = logL + log Normal13(z;0,I) - log(nuisance-support) - log q_v3(z)` (GitHub issue #280, comment 6875342212). F85 `raw_replay()` silently omitted `-log(nuisance-support)`.

**Actual repair:** require `--support-field` to be the *explicit original JSONL field* holding the logged support factor; abort if unspecified, missing, nonfinite, boolean, or if reconstructed full sample differs from stored `logweights`. No arbitrary support value is supplied. The exact raw field name cannot be inferred from a summary and must be inspected in original archived NPZ/JSONL. The default summary-only mode continues to work and retains the immutable historic `FAIL`.

**Local TDD:** four new synthetic tests failed against the former code (3 errors; one additional missing-support test failed due to missing argument); after repair all **18/18 PASS** including the 14 previous original checks. These tests prove only the implementation contract, **not a new native photon result**.

**Authenticity:** Windows SentinelX host was checked and is offline. Raw NPZ and JSONL were not available to this run; original historic 10,817 X-PSI photon likelihood calls remain **done**; the earlier seed 198301 remains **FAIL**. Full M–R and physical 7-EOS Bayes are not established. No changes to source model, raw data, samples, thresholds, or logweights.

**Next native run:** once original private files are accessible, inspect event keys and verify the exact native support field, then pass `--npz`, `--jsonl`, and `--support-field` to F85 CLI. Compare all 2048 original samples and fixed gates. Only a separately preregistered, genuinely independent heldout trial can validate a refitted proposal.
