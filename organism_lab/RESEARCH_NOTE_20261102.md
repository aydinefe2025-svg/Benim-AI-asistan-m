# Digital replication: research note (2026-11-02)

## What ran locally

The Organism Lab dashboard executed 30 paired seeds at five resource levels (0, 2, 5, 10, 20 units per tick), for 100 steps per world. The experiment uses a tiny virtual instruction set: a genome must execute `COPY_REST` and then `DIVIDE`; offspring inherit the sequence with a 2% per-opcode point-mutation probability. A matched control uses the same genome, resource budget, capacity, and seeds with division disabled. The browser displayed the computed table, the campaign was written to JSON and CSV, and SQLite contains the matching study ID `fb3e2350-dbfb-42ca-a529-0b94e8c523a5`.

The displayed mean final populations (replicating vs. division-disabled control) were: resources 0: 0 vs. 0; 2: 2 vs. 1; 5: 4.733 vs. 1; 10: 9.467 vs. 1; 20: 18.233 vs. 1. For this run, the estimated paired difference was positive at every nonzero resource level. This is evidence only about this specific toy simulation and its seeds. It does not demonstrate biological evolution, general intelligence, durable learning, or real-world robotics.

## What published work contributes

- Adami et al. exhaustively evaluated the length-eight Avida genome space (about 209 billion sequences) and found 914 self-replicators. Their result illustrates that replication depends on an explicit instruction architecture and its genotype–phenotype map; our three-opcode toy does not reproduce Avida's scale or findings. [Origin of life in a digital microcosm](https://pmc.ncbi.nlm.nih.gov/articles/PMC5686406/)
- Stepney and Hickinbotham argue that open-endedness needs both system-generic and system-specific analysis. A population increase alone is not an adequate open-ended-evolution claim. [On the Open-Endedness of Detecting Open-Endedness](https://pubmed.ncbi.nlm.nih.gov/36848499/)
- A 2024 in-vitro study reported self-replicating DNA in a liposome/PURE system accumulating mutations associated with selection advantage over ten evolution rounds. This is experimental synthetic biology, a different kind of evidence and system from this computer simulation. [Darwinian Evolution of Self-Replicating DNA in a Synthetic Protocell](https://pmc.ncbi.nlm.nih.gov/articles/PMC11494085/)

## Concrete next experiment

Before making any claim about open-endedness, expand the VM with variable-length genomes and an explicit read/write head, then add tests for copy fidelity, mutation neighborhoods, extinction, and parasite-like non-replicating genomes. Pre-register the metrics and compare several mutation rates over paired seeds. Keep any model-generated commentary separate from simulator outputs and reject contradictions. The current local Qwen check did contradict a computed zero-resource result and was discarded; the numeric table and raw run data remain intact.

## Files

- Dashboard campaign JSON: `organism_lab_output/fb3e2350-dbfb-42ca-a529-0b94e8c523a5.json`
- Raw per-seed CSV: `organism_lab_output/fb3e2350-dbfb-42ca-a529-0b94e8c523a5.csv`
- SQLite record: `organism_lab_output/research_studies.sqlite3`
- Independent CLI run: `outputs/genome-study-20261102/fe60ed0d-3953-4c06-8bc7-3122af66b4af.json` and `.csv`
