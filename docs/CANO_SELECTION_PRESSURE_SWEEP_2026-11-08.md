# CANO — Controlled cap/resource selection pressure sweep (8 Nov 2026)

**Topic:** `organism.digital` · **Goal:** diagnose why a genetic task advantage does not translate reliably into viable population growth · [Issue #413](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/413).

## Previous evidence and the actual defect

The earlier 450-run compositional task study had 87/90 paired seeds with equal final populations, including 65/90 both at cap 48 and 19/90 both at one-survivor floor. Its forensic audit found 55/90 pairs with a better composite-genome share but equal final population, and an average increase of ~30 task-rewarded organism-ticks alongside **1.48 fewer new births**. These *retrospective associations* cannot establish the cause of stagnation.

The current intervention is a **new experiment** using the exact pinned original `digital_vm.py` (GitHub blob `0ced308713956ebd43fa58ef29bb31502101d001`) and existing `compositional_transfer_study.py` (GitHub blob `8fd857a39404602b86e2ae40f731ca0819862085`). No existing code or live service was modified. The new module `selection_pressure_sweep.py` records first successful division, full population time series, sum of survivor-individual-ticks, births, and reward events over a matched reward/null counterfactual.

## Prospectively fixed design (before evaluating new seeds)

- Two **new** independent 30-seed partitions, `300..329` and `400..429`; no re-running old 0/100/200 seed partitions as new evidence.
- Original 4-locus founder `(COPY_REST, TASK_A, NOP, DIVIDE)` and two inherited interventions: `task_grammar` vs `core_protected`. First train each *once* with capacity 48/resources 1 for 120 ticks, A→B change after tick 40, mutation rate 0.08; for negative controls also train `no_mutation` and `no_division` from the same seeds.
- **Matched starting census:** take `n=min(12, alive_in_grammar, alive_in_core)` real genotypes spread evenly across sorted individual identifiers on each side; no replacement or artificial cloning. Both groups begin with exactly `n` individuals, each energy 3, mutation frozen. This is an engineered **post-training sampling intervention** and can lose rare genomes. If either group is extinct, both start empty (no fabricated organisms).
- All 9 prespecified evaluation cells: cap **12, 24, 48** × shared per-tick resources **0, 1, 4**. Every cell has a **C-reward-2** copy and otherwise identical **C-reward-0** null. Holdout lasts 20 ticks; task C is the engineer-defined conjunction A AND B in a functioning copyable genome. Original task grammar stays unchanged.
- **Primary cell fixed before computing data: cap24/resources1.** Main endpoint is paired *difference of causal lifts*: `[grammar (reward−null) total survivor-person-ticks] − [core (reward−null) total survivor-person-ticks]`. Also measure causal births, terminal population, time to first division, cap/floor occupancy. All 8 other grid cells are **exploratory**, not 8 more chances to declare a win.
- **Strict acceptance per distinct 30-seed cohort:** at least 50% of **all** seeds have strictly positive primary causal-time difference, one-sided sign-test p<0.05 on nonzero pairs, descriptive 95% normal-approx lower bound >0, causal births lower bound >=0, all controls pass. Both cohorts must pass. These tests are about simulator-defined metrics, **not** general intelligence.

## Observed results (Python 3.13 local; GitHub Python 3.11/3.12 verification separate)

| Primary cell (cap24/resources1) | Seeds 300–329 | Seeds 400–429 |
|---|---:|---:|
| Positive paired causal survivor-time effect | **9/30** | **10/30** |
| Negative / tied | 2 / 19 | 4 / 16 |
| Mean causal survivor-individual-ticks difference | −0.667 | +10.767 |
| Approx. 95% CI for primary effect | **−8.016 .. +6.683** | **−3.613 .. +25.146** |
| Mean paired causal births effect | −0.900 | +0.700 |
| Approx. 95% births CI | −1.892 .. +0.092 | −0.955 .. +2.355 |
| Rewarded terminal population tied between methods | **29/30** | **28/30** |
| Strict primary acceptance | **FAIL** | **FAIL** |

**What changed in measurement:** The prior terminal-population comparison was largely blind to initial resource and cap pressure; the new study captures time-to-first-division, total survivor-time, and reward-minus-null effects at three distinct levels of both capacity and resource budgets. Even with matched initial censuses, the primary-cell outcome is too sparse and uncertain to establish broad task advantage. A causal difference between an internal reward copy and its zero-reward clone is an engineered counterfactual, **not** evidence that the selection mechanism evolved autonomously.

### Cross-grid sensitivity (exploratory)

- At cap12/resources0, mean paired causal time effect (grammar minus core): −2.467 and +5.533 for the two cohorts. At cap48/resources4 it becomes +0.900 and +22.267. These are sensitivities, **not** proof of a monotonic response or a predeclared significant result.
- Rewarded terminal-population ties remain 28–29/30 across all cap/resource settings in these partitions. Causal person-time may reveal dynamics when terminal counts are tied, but its own seed-level statistical uncertainty remains large.
- Resource4 allows first division in both methods in all 30 seeds for cap24 and cap48, illustrating that task-specific rewards are no longer uniquely needed for growth when shared resources are plentiful. Reward=0 clones explicitly control for this channel.

## Verification, limits and recording

- **Real RED→GREEN:** initially the first-division behavioral test raised `NotImplementedError` before implementation; the newly written time-course matched the legacy `holdout_composition` for both reward0 and reward2. Eight new local unit tests passed and all eight prior compositional-transfer tests passed with the **exact Git blob-matched VM**.
- New code is `organism_lab_cloud/organism_lab/selection_pressure_sweep.py`, tests `organism_lab_cloud/organism_lab/tests/test_selection_pressure_sweep.py`, independent CI workflow `.github/workflows/cano-selection-pressure-sweep.yml`.
- Immutable SHA-256 + full deterministic recomputation of two per-seed machine-readable JSON reports; forged digest with altered data is rejected; saving a different report at the same filename refuses overwrite.
- Fitness is artificial; this is a time-course simulation and a post-training sampling intervention. Choice of 60 finite pseudorandom seeds is not external scientific replication. Multiple grid conditions are not confirmatory independent tests. A reported improvement in this model cannot establish AI weight learning, biology or physical robot behavior.
- **Remaining actual blocker:** Even when survivor-time is observed, no majority of seed pairs obtains a robust grammar-vs-core advantage. More nuanced resource competition and task-cost modeling must be tested prospectively; do not tune thresholds to these observed results.

**Storage boundary:** Complete, immutable per-seed JSON reports remain inside the main ChatGPT research Library ZIP (`CANO_Selection_Pressure_Sweep_2026-11-08.zip`). GitHub stores the new code, tests, reproducibility workflow, narrative and pinned digests, avoiding 700KB duplicate history. CI recomputes both full files from source and compares both the inner report digest and complete-file SHA-256 to the pinned manifest. No report is claimed to be directly stored as a standalone JSON in GitHub.
