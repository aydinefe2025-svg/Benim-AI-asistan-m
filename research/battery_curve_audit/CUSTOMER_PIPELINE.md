# CANO battery customer-local audit — one-command pilot

**Status:** offline preflight / screening prototype, **not** a certified battery health analyzer, independent measurement certificate, commercial service, or customer-site acceptance.

This is the missing orchestration step between the already tested components:
`customer_preflight.py` (CSV schema, strict compatible physical units, non-invented short rows), `numeric_equivalence_guard.py` (exact Decimal numeric equality despite different export text), `near_duplicate_guard.py` (conservative voltage-vs-time near-match candidates), and candidate-connected, whole-cell train/validation/test splitting.

## Run without sharing customer measurements

Use Python 3.12+ and local, authorized CSV files only. Create `manifest.json` at the same directory as the files, with *relative paths*:

```json
{"schema":"cano.battery.customer-files.v1","files":[
 {"path":"battery_A.csv","cell":"A","mode":"dchg"},
 {"path":"battery_B.csv","cell":"B","mode":"dchg"},
 {"path":"battery_C.csv","cell":"C","mode":"chg"}
]}
```

Run from the repository root (no network or third-party dependency):

```sh
python research/battery_curve_audit/customer_pipeline.py \
  --manifest ./local-data/manifest.json \
  --root ./local-data \
  --summary ./local-safe-summary.json
```

The program returns **exit 2** for a duplicate/near-match review, invalid input, or insufficient independent groups, even if it successfully writes an aggregate report. `--report-only` explicitly permits exit 0 to *inspect* that report; it **never** approves a train/test split. The public summary contains only counts and unit tags, not measurements, file names, customer aliases, source hashes, or trace SHA-256 values.

A genuinely private holdout file can be requested explicitly:

```sh
python research/battery_curve_audit/customer_pipeline.py \
  --manifest ./local-data/manifest.json --root ./local-data \
  --summary ./summary.json --private-split ./sensitive-holdout.json
```

This opt-in JSON contains cell aliases and trace SHA-256 hashes, and is marked `NOT_CERTIFIED` even if no candidates are detected. Do not publish it without consent. The script creates output files in exclusive mode (`0o600` on POSIX); existing files and any source CSV/manifest path are never overwritten. On Windows, folder ACLs must be configured separately: do not treat `0o600` as a Windows access-control guarantee. Output folders must already exist.

## Safety and scope

- Strict units are inherited from the existing parser: one consistent time/voltage pair across files (`h`, `s` or `ms`; `V` or `mV`), **no silent unit conversion for identity hashing**. Near screening converts `mV` to `V` so 2 mV stays 2 mV; time axes are already uniform. Wrong/mixed unit declarations are blocked.
- No missing timestamp or voltage is filled with zero. Complete trailing omitted column pairs are preserved; malformed/missing half-pairs are rejected.
- Exact Decimal equality is distinct from near equality. Near candidates require the same charge/discharge mode, at least 100 measurements, nonflat traces, endpoints within 0.5%, and at most 2 mV piecewise-linear difference over original knots. Identical numerical curves form groups even when CSV formatting differs. Near candidates are **review-only** and not evidence of deliberate copying.
- All exact/numeric and near links become a transitive connected component of cells. Each component's entire trace history goes to only one split; if fewer than three groups exist, the tool **blocks split creation**, never fabricates statistical independence.
- The pilot caps processing at 120 traces, to avoid unbounded quadratic comparisons. Larger datasets require separately controlled batching and acceptance.
- A negative screen does not prove physically independent samples, exclude unrecorded shared batches, or validate any battery SOH/SOC prediction. Real lab technician labels, instrument metadata and false-positive/false-negative rates remain unverified.
- Raw measurement pairs never leave the local Python process. However, local input file and manifest access still require appropriate customer permissions. This tool does not upload to Notion, GitHub, Render or Neon.

## Repeatable verification

```sh
python -m unittest discover -s tests -p 'test_battery_customer_pipeline.py' -v
python -m py_compile research/battery_curve_audit/customer_pipeline.py
```

GitHub CI also runs the same command against a manifest generated from the 20 Git-blob-pinned public CSVs published by POLITEHNICA Bucharest, validates its aggregate counts, and stores the redacted summary in a short-lived Actions artifact. That CI exercise is a **published-source regression**, not a paid customer deployment or a field trial.

**Data attribution:** public test dataset [BulyK47/battery-datasets](https://github.com/BulyK47/battery-datasets), DOI [10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66), CC BY 4.0, credit required. Original audit scripts and metadata remain available in repository history. Customer-provided data are governed by their own permissions.
