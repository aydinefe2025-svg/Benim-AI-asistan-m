# Cross-publisher SOC–voltage screening benchmark (19 November 2026)

This is a **second experimental publisher** beyond the University POLITEHNICA Bucharest time–voltage CSV dataset. This cross-publisher *research screen* is NOT customer field acceptance or multi-lab calibration.

## Measurements, provenance and license
David-EIPI, Experimental voltage–state-of-charge data for lithium-ion cells:
https://github.com/David-EIPI/lithium-battery-soc

The publisher documents 17 physically different cylindrical Li-ion cells (mixed new/reclaimed), discharged at approximately 200 mA on an Opus BT-C3100, with terminal voltage recorded by a separate logger. The data are **postprocessed SOC-fraction–voltage curves**, 51 points per cell, NOT raw time series. The original paths are discharge/01.dat to discharge/17.dat.

License: BSD 2-Clause; full license notice is preserved alongside the copied measurements at fixtures/DAVID_EIPI_BSD_2_LICENSE.txt. The source 17 files are copied verbatim into fixtures/external_soc_david_2026.json with their individual original Git blob SHA-1 identifiers. Each SHA is recalculated and checked before benchmark execution. The benchmark uses 17×51 = **867 real SOC/V pairs**.

## Real distinct-cell negative screen
All 17 choose 2 = **136 distinct-cell pairs** are compared on a *shared SOC axis* using an exploratory 2 mV aligned-SOC voltage RMSE cutoff. Same-publisher cell pairs are NOT statistically independent samples (each cell appears in multiple pairs). A triggered pair is an inspection candidate, not evidence of copying; untriggered comparisons do not prove physical independence. Do NOT report binomial confidence intervals or a population field false-positive rate from these 136 dependent pairs.

## Controlled positive screen
Each of the 17 measured curves has three **generated controls**, not independently acquired physical duplicate measurements: (1) exact copy; (2) equivalent Decimal numbers with different lexical formatting; (3) every voltage increased by +1 mV. Total 17×3 = **51 controls**. Their detection is a unit test on a genuine measured base curve; it is not a lab-validated real-copy recall estimate.

## Critical domain constraint
The real curves' x-axis is **SOC fraction**, not seconds or hours. The research-only metric here is aligned-SOC voltage RMSE, which differs from the existing time-based near_duplicate_guard.py algorithm (different axis, endpoint tests and calibration). Passing this external benchmark MUST NOT be cited as validation of the production time-series near detector. The benchmark never passes SOC as time and cannot be called by the customer time CSV pipeline without a domain mismatch.

## Commands
Run from the project root:

    python -m unittest discover -s tests -p 'test_battery_cross_publisher_soc.py' -v
    python research/battery_curve_audit/cross_publisher_soc_benchmark.py --output external_soc_benchmark.json

The report has source, units/axis contract, 136 negatives, 51 controlled positives, nearest observed distinct pair, decision and limitations. It refuses to overwrite an existing report.

## Explicit limitations
- One different publisher / instrumentation source, **not** multiple independent field labs.
- Real negative cell identities, **synthetic manipulated positives**, so no real duplicate labels.
- No independent customer consent, field negatives/positives, per-device error rates, SOH or capacity estimation, paid customers or revenue.
- Original university source 20 CSV and 60 trace findings remain separately attributable; not a new detection result here.
- No modification to CANO Render / Neon services or the main time-series customer algorithm.
