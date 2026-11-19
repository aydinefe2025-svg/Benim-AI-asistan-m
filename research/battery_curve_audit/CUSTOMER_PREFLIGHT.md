# CANO battery customer CSV preflight (offline pilot)

Requires Python 3.12; no dependencies or outbound network access. Map locally owned or
authorized 2/4/6-column timestamp-voltage CSVs in JSON:

```json
{"schema":"cano.battery.customer-files.v1","files":[
 {"path":"cellA.csv","cell":"A","mode":"dchg"},
 {"path":"cellB.csv","cell":"B","mode":"dchg"},
 {"path":"cellC.csv","cell":"C","mode":"chg"}
]}
```

Run from repository root:

```sh
python research/battery_curve_audit/customer_preflight.py --manifest manifest.json --report report.json
python research/battery_curve_audit/customer_preflight.py --manifest manifest.json --report report.json --split holdout.json
```

One to three timestamp/voltage pairs per CSV header, strict positive-length/finite
measurements and monotonic time. Trailing entire unused column pairs can be
omitted, but unmatched time/voltage and escaping file paths are rejected.
`--split` requires three independent connected cell groups, keeps ALL traces
from any cell together, and keeps exact curve duplicates together across cells.
Report-only output does NOT certify train/test independence.

No raw measurement pairs are written to audit JSON or transmitted to a service;
**file names and cell aliases and content hashes are still sensitive**. Do not
publish customer reports without explicit authorization. Exact source-text
equality misses near-duplicates/resampling/normalization and shared-device
dependence; a missing match is not a certificate of independence.

This is an experimental data-integrity CLI, not an accredited instrument,
battery-health estimate, validated field service or commercial acceptance.
Publisher test data: [POLITEHNICA Bucharest](https://github.com/BulyK47/battery-datasets)
([DOI 10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66));
source CSV data CC BY 4.0 with attribution. Real-data CI checks original pinned
20 publisher files; test suite uses synthetic customer fixtures.
