# CANO Battery Provenance: unicode/case/padding alias safety (synthetic pilot)

**Goal:** `battery-field-provenance-alias-1200-20261119` — eliminate a false pilot-clean decision caused by metadata spelling variation, without claiming laboratory proof.

## New reproducible failure

Previous `field_pilot_evidence.assess()` grouped shared instrument (`device`), `batch` and acquisition `campaign` values as **literal strings**. The same possible serial `INSTR-A` and `   instr-a   `, or the same batch typed in fullwidth Unicode (`ＢＡＴＣＨ－Ａ`), could cross declared train/test partitions without a metadata-leakage flag. A synthetic four-cell case returned `PILOT_METRICS_ONLY` when review was required. Before implementation, three focused public-interface regression tests reproduced this false-green decision (`FAILED (failures=3)`). A subsequent invisible `\u200b` format-character case also failed until an explicit reject was added.

## Implemented safety rule

For **provenance metadata only**, match grouping keys through Python `unicodedata.normalize('NFKC', value).strip().casefold()` and reject Unicode categories `C*` (including invisible formatting or control characters). This is conservative *review* grouping, not a conclusion of physical identity. Customer source CSV, original audit SHA, cell alias strings, timestamps, voltages and reviewer labels remain unchanged. Same-key metadata in two different train/validation/test partitions forces `BLOCK_PROVENANCE_LEAKAGE`; within the same partition it connects the provenance component without falsely making a cross-partition claim. It may overgroup genuinely distinct **case-sensitive** serials; such ambiguous cases must be resolved with trusted instrument or batch registration records, never silently accepted as independent.

This is not a universal homoglyph detector: arbitrary typos and visually confusable letters from distinct scripts can still evade NFKC. A negative software match cannot establish physical independence or that a human authorization is authentic.

## 1,200 synthetic stress scenarios

```sh
python research/battery_curve_audit/provenance_alias_lab.py \
  --trials 50 --seed 20261119 --output provenance-1200.json
python -m unittest discover -s tests -p 'test_battery_provenance_aliases.py' -v
python -m unittest discover -s tests -p 'test_battery_provenance_alias_lab.py' -v
```

3 source fields × 6 alias transforms × 50 generated cases = **900** intentionally matched-alias cross-partition examples; **900/900** were blocked for provenance review after the fix. Two strictly distinct textual-control patterns × 150 = **300** negative controls; **300/300** were not cross-partition blocked. All **1,200** are synthetic metadata, NOT real devices, measured batteries, independent field labels, or calibrated error-rate estimates. The report contains only counts and scenario names; source serials are not included.

The six generated transformations are lowercase, ASCII outer padding, NFKC fullwidth forms, Unicode outer padding, fullwidth lowercase, and combined padding/fullwidth lowercase. The distinct controls use changed punctuation (double hyphen vs single hyphen; underscore vs hyphen). The deterministic seed and code specify the distribution. Do not use fractions here as generalizable model precision/recall.

## Evidence and release safety

`provenance_alias_lab.py` uses Python standard library only and writes aggregate JSON with `O_EXCL`/POSIX `0600` without overwriting evidence. Existing `field_source_csv_bridge.py` still revalidates raw CSV SHA and bound audit receipt; this change adds conservative metadata comparisons **after** the existing source-bound protections. Technical success remains `field_acceptance=NOT_ESTABLISHED` on all paths. No customer files, paid service, production deployment, hardware measurement, or verified technician signature is required or claimed. For real-world acceptance, independently verify instrument identifiers, sample/batch chain, campaign IDs and two technician reviews with lab source documents before certification.

Publisher benchmark context remains [POLITEHNICA Bucharest/BulyK47](https://github.com/BulyK47/battery-datasets), DOI 10.21227/cm0f-jg66, CC BY 4.0, but these 1,200 scenarios do not use those original measurements.
