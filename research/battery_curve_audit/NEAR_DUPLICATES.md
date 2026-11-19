# Battery near-curve screening — 19 November 2026

**Independent work key:** `research.opportunities / battery-20261119-near-curve-review-and-safe-holdout-v2`.
**Data:** POLITEHNICA Bucharest via [BulyK47/battery-datasets](https://github.com/BulyK47/battery-datasets), [DOI:10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66), **CC BY 4.0**; credit the original publisher and authors when redistributing data.

The 18 November pinned 20-file/60-trace exact-copy audit and 19 November PR #637 cell-level partition are prerequisites, not new discoveries. They are preserved. The new detector reads the exact original publisher files in memory and creates a **screening report**, not a declaration of physical duplicates or scientific independence.

## Screening criterion (deliberately narrow)

Compare only *distinct cells, same charge/discharge mode* with at least 100 measured pairs each, non-flat voltage range >=50 mV, and both absolute time endpoints within 0.5% of the longer duration. Interpolate each trace linearly onto 65 quick checkpoints, then on the union of **every actual measured time knot** within their overlap. Record a candidate only when the maximum absolute voltage difference is <=2 mV at all these knots. The exhaustive second check catches short voltage spikes that would be missed by low-resolution resampling. No extrapolation, no nonlinear time-warp, no zero filling. Exact hash duplicates are handled by PR #637 instead.

These fixed 2 mV and 0.5% thresholds are provisional **screening rules**; they have not been calibrated to customer instruments. Flat curves, shifted times, or large sampling gaps can produce blind spots. Different chemistry, temperature, device, cycle, source session or batch might still be statistically dependent; a nonmatch is not proof of independence.

## Operational command (only approved, hash-pinned publisher CSVs)

```bash
python research/battery_curve_audit/original_20261118.py --download --data-dir battery-data --output-json battery_audit.json
python research/battery_curve_audit/independent_holdout.py --audit-json battery_audit.json --output-json battery_holdout.json
python -m unittest discover -s tests -p 'test_battery_near_duplicate_guard.py' -v
python research/battery_curve_audit/near_duplicate_guard.py --data-dir battery-data --audit-json battery_audit.json --holdout-json battery_holdout.json --output-json near_screen.json
```

By default, legitimate screening findings are emitted into JSON, not swallowed as a fatal CI infrastructure error. The `--strict` flag blocks downstream model acceptance (exit 2) whenever any near candidate needs expert review or fewer than 3 independent component groups remain; it also rejects bad input/hash/split evidence. Customer/production workflows **must** require verified artifact provenance and honor this strict decision.

The tool computes transitive components across both exact hash matches and near candidates; if three nonempty train/validation/test groups remain, it proposes a deterministic **candidate-safe** group-level split. The previous exact-only split is *not* assumed safe when a near candidate crosses partitions. A proposal may remove samples from independent holdouts; a lab technician must still review whether apparent similarity reflects legitimate controlled experiments, formatting, shared data, device reuse or copying. With fewer than three components it refuses to invent a safe split.

**Evidence acceptance**: CI downloads all 20 pinned publisher CSVs and verifies the source auditor's 60 traces and 703,657 measured pairs; unit tests check resampled near matches, single-point spikes, time shifts, flat curves, short CSV rows, transitive graph grouping and tampering. Include `battery_near_screen.json` with the publisher audit and split artifacts. This is not a SOH model or commercial pilot, nor verification of zero false positives. Before selling, obtain customer-permitted labeled source recordings from separate instruments/batches, calibrate thresholds and measure false-positive/false-negative rates under a locked protocol.