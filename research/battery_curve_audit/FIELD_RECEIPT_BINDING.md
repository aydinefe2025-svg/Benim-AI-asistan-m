# CANO — laboratuvar makbuzu / saha defteri bağlama kapısı

This is an **offline source-and-annotation linkage audit**, NOT customer-site acceptance, statistical independence certification, accredited battery health measurement or SOH prediction. Python 3.12+ standard library only.

## What it closes

`integrated_customer_gate.py` re-runs the time/voltage CSV validity, source fingerprint, exact numeric and conservative near screening before constructing a *candidate* group-atomic split. Separately, `field_pilot_evidence.py` checks lab device, batch, campaign and reviewer metadata, but used to accept self-asserted cell assignments and a syntactically valid 64-character receipt without comparing either against the real CSVs. The gap permitted a false narrative that a self-asserted field ledger validated the *same* data split.

`field_receipt_binding.py` **does not trust the ledger's asserted split**:

1. SHA-256 of the complete exact UTF-8 JSON **audit report file bytes** must equal `ledger.audit_receipt_sha256` (no canonicalization, no guessing and no remote service).
2. `integrated_customer_gate.verify_report()` independently re-audits **all original local source CSV files**, their units and all reported results; a report altered to look successful is rejected, even if its hash is recomputed.
3. Every ledger cell identifier and train/validation/test partition must exactly equal the verified audit's independently grouped split assignments; missing/extra cells or contradictory partitions are rejected.
4. The original field-pilot `assess()` reruns device, batch, campaign and technician consensus leakage checks. Source `REVIEW_REQUIRED` **always** yields `BLOCK_AUDIT_REVIEW`, regardless of optimistic field metadata. Metadata leaks cause `BLOCK_PROVENANCE_LEAKAGE` even when source screen is clean.
5. The output is *redacted aggregate JSON*: no raw readings, names, receipt digest, file paths, reviewer IDs, device, batch or campaign identifiers. It is created only if the output does not exist and never overwrites source, ledger, audit, manifest or existing output files. POSIX permission 0600; Windows ACLs require user management.

## Example — local-only workflow

First create the private source audit using the existing verified gate:

```sh
python research/battery_curve_audit/integrated_customer_gate.py \
  --manifest ./authorized/manifest.json --root ./authorized \
  --report ./private-source-audit.json
```

The site operator must create its **own authorized field ledger** according to `FIELD_PILOT_EVIDENCE.md`, copying **exact** cell partition assignments from the audited report (only a proposal when the source has review flags), and set `audit_receipt_sha256` to the SHA-256 of the **exact** bytes of `private-source-audit.json`. This can be computed locally using `python -c "import hashlib;print(hashlib.sha256(open('private-source-audit.json','rb').read()).hexdigest())"`. These records and receipts are private; never publish them.

Then:

```sh
python research/battery_curve_audit/field_receipt_binding.py \
  --manifest ./authorized/manifest.json --root ./authorized \
  --audit-report ./private-source-audit.json \
  --ledger ./authorized-private-field-ledger.json \
  --summary ./redacted-linked-evidence.json
```

Exit `0` is **only** `PILOT_ONLY_NOT_CERTIFIED` (screening and grouping are consistent, no field certificate). Exit `2` is review/block or failed linkage. A blocked evaluation may produce a redacted summary for investigation; it must **never** create an accepted train/test split or signal field approval. No customer data are uploaded or sent to GitHub, Notion, Render or Neon.

## Empirical verification and limits

The new 10 synthetic tests start RED (`NotImplementedError` in an unimplemented module) and pass GREEN after implementation, covering forged SHA receipts, tampered report with updated SHA, changed source bytes, mismatched partition, omitted cells, metadata cross-split, an actual known duplicate in synthetic customer inputs, insufficient groups, safe output behavior and a clean-not-certified path. The existing 112 synthetic tests in the released pilot were also exercised locally: combined `122/122` PASS. These are software tests, not measured clinical/lab performance or real customer labels.

The original published baseline remains POLITEHNICA Bucharest/BulyK47 [DOI 10.21227/cm0f-jg66](https://doi.org/10.21227/cm0f-jg66), CC BY 4.0; a separate 17-cell SOC-axis publisher benchmark uses a different physical domain. Neither public benchmark establishes third-party technician ground truth, lab authorization or the commercial field false-alarm/false-negative rate. `site_authorization.permitted` still means **user-attested, not independently validated**.
