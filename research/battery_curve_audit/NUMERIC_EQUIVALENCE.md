# Numeric equality add-on (19 November 2026)

This optional, **offline** battery CSV add-on detects an additional leakage class:
CSV measurements numerically equal but spelled differently (`3.4`, `3.400`,
`34e-1`, `+3.40e0`). The 18 Nov exact-text SHA audit and subsequent near-curve
2 mV screening remain distinct checks. Numeric equality is **not** a tolerance,
interpolation, or accusation of copied observations.

The program runs `customer_preflight.audit_customer` first, retaining original
file SHA-256, trace text SHA-256, row counts, sources and comments. It then
parses the same local customer CSVs, checks all source hashes are unchanged,
calculates exact `Decimal` coefficient/exponent normalized time–voltage SHA-256
per trace, and groups all equal numeric traces. A separate validated holdout
can be generated via the existing `independent_holdout.py` (whole-cell connected
components). **Never** interpret a mere report-only run as a leakage-safe split.

No network calls, paid dependencies or raw measurement export. The JSON report
still includes customer-sensitive filenames, cell aliases and hashes. Do not
publish customer reports without consent. This is not a battery-health
measurement, manufacturer certification or proven customer acceptance.

```sh
python research/battery_curve_audit/numeric_equivalence_guard.py \
  --manifest customer_manifest.json --root ./customer_csv \
  --report numeric_audit.json --holdout numeric_holdout.json
python -m unittest discover -s tests -p 'test_battery_numeric_equivalence.py' -v
```

Only run the holdout when at least three independent connected cell groups
remain. If fewer groups exist, the tool exits with review required. Future
work: instrument-specific timestamp/voltage precision and customer-site false
positive/false negative evaluation. No physical independence inference is
possible from text/numeric equality alone.

Original published data example: [POLITEHNICA Bucharest / battery-datasets](https://github.com/BulyK47/battery-datasets), [DOI 10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66), dataset CC BY 4.0, attribution required.
