# Self-replicating organisms — standing research objective

The user explicitly requests **self-replicating organisms** as a core, continuing objective. Do not drop this from future planning.

## Distinct research tracks

1. **Digital organisms:** bounded autonomous replication in a simulated environment, with energy/resource accounting, heredity, mutations, selection and reproducible experiments.
2. **Software agent colonies:** agents may spawn new *instances* under explicit quotas and measured task demand; spawning is not model training or autonomous capability improvement.
3. **Modular robotics:** simulate modular assembly, self-reconfiguration and hypothetical reproduction before any physical hardware trials.

## Required evidence

- Track population, generation, ancestry, resources, survival, diversity and task performance per generation.
- Define a reproduction condition and cost; no free infinite spawning.
- Enforce population, time, compute and budget limits; allow emergency stop.
- Compare against non-replicating controls and fixed random seeds.
- Label simulation separately from physical realization; do not claim living cells or real robots were created.

## Milestones

- [x] Implement deterministic resource-limited digital organism world (`digital_vm.py`, CI #191).
- [x] Add reproduction, inheritance, mutation and lineage tests (`test_digital_vm.py`, `test_reproduction_study.py`).
- [x] Add metrics and paired division-disabled control comparisons (`reproduction_study.py`; five resource levels, 30 seeds).
- [x] Add a local Streamlit visualization and JSON/CSV/SQLite export (`dashboard.py`).
- [x] Verify study persistence by independent replay across JSON/CSV/SQLite (`study_verifier.py`, CI #191).
- [x] Verify deterministic genome checkpoint restore and idempotent advance (`genome_checkpoint.py`, CI #191).
- [ ] Explore modular robot self-assembly in simulation.
- [ ] Evaluate improvements before adding live model providers or deployment.

This roadmap does not authorize uncontrolled deployment, physical biological experiments or paid resource consumption.
