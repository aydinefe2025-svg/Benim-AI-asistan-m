# CANO battery: integrated offline preflight

Free stdlib-only Python 3.12+ prototype. No telemetry, cloud upload, external API, or hidden package install. Use only on files you are allowed to process. Customer aliases and hashes in reports are **confidential**, even though raw time-voltage samples are omitted.

## Inputs

`manifest.json` beside the authorized customer CSV files (or provide `--root`):

```json
{"schema":"cano.battery.customer-files.v1","files":[
  {"path":"cell-A.csv","cell":"A","mode":"dchg"},
  {"path":"cell-B.csv","cell":"B","mode":"chg"}
]}
```

Headers must declare consistent units on every file and column: timestamp `h`, `s`, `ms` and voltage `V` or `mV`. Unit mixing fails instead of silently converting CSVs. Missing trailing unused 2-column pairs are supported, never filled with zero.

## One safe command

Run with the `research/battery_curve_audit/` files from the same GitHub commit. The full split is only emitted when all evidence gates are clear:

```sh
python research/battery_curve_audit/integrated_customer_gate.py \
  --manifest manifest.json --root ./authorized-csvs \
  --report ./private-battery-report.json \
  --accepted-split ./accepted-split.json
```

Exit 0 means **PASS_SCREEN_ONLY**, *not* a certificate of experimental independence. Exit 2 means **REVIEW_REQUIRED** or **BLOCK_INSUFFICIENT_GROUPS**, and there is **no accepted split**. A proposed transitive group holdout may remain in the private report for technician review. `--verify-report old_report.json` reruns original local files and compares all evidence, including the proposed split. All split-creating legacy calls through `customer_preflight.py --split` are deliberately rejected; that unsafe text-only acceptance path is disabled. `customer_preflight.py --report` remains supported for read-only baseline provenance. Likewise `numeric_equivalence_guard.py --holdout` is disabled because it skips the near-curve gate; `numeric_equivalence_guard.py --report` remains read-only.

## Applied layers

1. Strict path containment, CSV column integrity, finite/nonnegative numbers, monotonic timestamps, and explicit uniform units; per-file source SHA-256.
2. Exact raw-text and exact Decimal-normalized (`3.4 == 3.400`) content fingerprints, with transitive grouping across *all* traces of any linked cell.
3. Review-only piecewise-linear near-match candidates: across different cells but **same mode**, at least 100 points, voltage span at least 0.05 V, endpoint separation at most 0.5% of duration, maximum union-knot distance at most 2 mV (after h/V unit conversion). Never silently accept underlength or flat traces.
4. Group-atomic train/validation/test holdout verified independently; if fewer than three cell groups survive, block rather than inventing independent sets.

Bounded by 120 curves and 1,000,000 point-pairs per run, max file 30 MB and max 1,000 explicitly mapped CSVs. Very large jobs fail closed. No support for cross-mode similarities, calibration, resampling beyond the candidate screen, or independent-machine/same-batch provenance: all require explicit lab review. An exact match or near candidate is *not* evidence of fraud. Real test baseline: [BulyK47/POLITEHNICA Bucharest battery data](https://github.com/BulyK47/battery-datasets), DOI 10.21227/cm0f-jg66, source CC BY 4.0 attribution required.

### Validation scope

Synthetic adversarial tests are not customer tests. On the original publisher dataset the known APR1/APR2/APR3 DC1 triplet must produce **REVIEW_REQUIRED**, **not** an accepted train/test split. A plausible 6/2/2 *proposed* grouping may be reported, but must not be called field or paid acceptance. No battery SOH calculation or physical fault diagnosis is performed.
