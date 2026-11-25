# CANO EPS Lab V4: measured I–V curve analysis

Historical laboratory benchmark, not fault labels or field qualification. Source pin in `fetch_benchmark.py`. Fit and holdout split within the same curve, endpoints in training. Python 3.11, NumPy 1.26.4 and SciPy 1.13.1 for reproducibility. 

Run `python fetch_benchmark.py`, `python -m unittest -v test_pv_measured`, `python run_benchmark.py`; `python analyze_csv.py your.csv --train 8 --out IV_RESULT.json` accepts columns V,I_A. `python make_viewer.py` generates a local viewer (precomputed results). No instrument control. Real source acquisition via `sandia_ingest.py` verifies archive CRC and records SHA-256, does not silently match modules by file names. Sandia source CC BY 4.0, https://data.openei.org/submissions/8378. Benchmark source citations: https://doi.org/10.3390/math13010019 and https://doi.org/10.1038/s41598-025-34584-1.
