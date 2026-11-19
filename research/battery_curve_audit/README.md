# Battery curves: independent holdout acceptance gate (2026-11-19)

**Scope:** research.opportunities | `goal_key=battery-20261119-cell-connected-exact-curve-holdout`  
**Source:** POLITEHNICA Bucharest, [BulyK47/battery-datasets](https://github.com/BulyK47/battery-datasets), DOI [10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66), **CC BY 4.0** (credit the dataset).  
**Original 18 Nov Library script SHA-256:** `6ca0c940d1b34ddfab99b7cfc9d6d2f3a92dfea20fdfaea0bad322b3e037fc90` (10,505 bytes, code preserved exactly).  
**Original script in this branch:** `original_20261118.py`; it pins all twenty original CSV Git blob IDs, rejects changes, preserves 2/4/6-column charge rows without zero-filling, and emits complete 60-trace evidence.

## New acceptance test

An exact curve hash creates an edge between the cells that own that curve. The guard joins all connected cell identities, then puts each whole group (including every charge and discharge trace for its cells) into **one** train/validation/test partition. It rejects mismatching evidence, repeated or missing trace IDs, partial cells, overlapping exact hashes, forged group graphs, and an empty partition. A fixed seed makes the split reproducible.

```sh
python research/battery_curve_audit/original_20261118.py --self-test
python -m unittest discover -s tests -p "test_battery_independent_holdout.py" -v
python research/battery_curve_audit/original_20261118.py --download --data-dir battery-data --output-json audit.json
python research/battery_curve_audit/independent_holdout.py --audit-json audit.json --output-json holdout.json
python research/battery_curve_audit/independent_holdout.py --audit-json audit.json --verify-json holdout.json
```

The GitHub workflow `battery-curve-audit.yml` executes this on a clean runner, checks the previously recorded **20 files, 60 traces, 506,141 discharge and 197,516 charge pairs, and 6,608 valid short charge rows**, and uploads its JSON receipt. A PR/workflow definition itself is **not** proof of a successful independent real-data rerun; read the workflow log and artifact before marking that acceptance PASS.

## Scientific and product boundaries

- Prior source-data inspection found one exact triplet, APR-1/2/3 DC1, each 3,764 pairs. The cause is undetermined; no misconduct allegation.
- Equal hashes here mean equal **published text pairs**, not automatically identical physical test provenance.
- Different hashes do **not** exclude near-duplicate traces, shared operating history, correlated batches, resampling leakage, or hidden labels. For genuine independent model evaluation, lab staff should also separate device, batch and acquisition campaign and audit derived features.
- No battery health/SOH model, customer acceptance, lab certification, sales, or revenue is established.
- No real customer data in CI, no secret required, no production Streamlit/Render/Neon code changes.

**Source audit:** [Notion canonical opportunities notebook](https://app.notion.com/p/4092bd61682a81759762f2911defaa57). Keep the prior 18 Nov acceptance; this 19 Nov gate is a new dependent product-engineering task, not a duplicate discovery.
