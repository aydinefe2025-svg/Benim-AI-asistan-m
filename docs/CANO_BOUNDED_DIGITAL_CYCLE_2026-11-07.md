# CANO calendar-driven digital reproduction (offline)

This is a **bounded digital organism simulation**, not physical or biological self-replication and not the creation of autonomous externally connected AI workers. It extends the existing `organism_lab.genome_checkpoint` replay-verifiable checkpoint rather than reimplementing its genome engine.

Every UTC date maps to an exact fixed target tick (8 ticks per day from 2026-11-07). Reruns of the same date are byte-for-byte idempotent. Reports have a division-disabled control, a full snapshot SHA-256, and a self-digest. Both reports and the checkpoint are read back. State is persisted in a dedicated Git branch by the workflow, not transient GitHub Actions artifacts. No secrets or network calls in the simulation; hard population maximum 24 and finite checkpoint horizon of 10,000 ticks.

Local run from repository root:

```bash
python -m unittest organism_lab.tests.test_calendar_cycle -v
python -m organism_lab.calendar_cycle --day 2026-11-07 --state-dir /path/to/persistent/state
python -m organism_lab.calendar_cycle --day 2026-11-07 --state-dir /path/to/persistent/state
python -m organism_lab.calendar_cycle --day 2026-11-08 --state-dir /path/to/persistent/state
python -m organism_lab.genome_checkpoint verify /path/to/persistent/state/genome-state.json
```

A dedicated GitHub Actions workflow is intentionally nonproduction. Daily trigger plus manual dispatch; only the simulation state branch is changed; reproducible source stays on main. If that branch or permissions are absent, the workflow fails closed. Daily experiment creates no new external agent, pays no cloud vendors and cannot access hardware. GitHub hosted runner minutes still count against the repository's plan allocation.

Known limitations: no model training, no independent worker, no full learning gain, no physical robot; daily schedule subject to GitHub Actions delay/disable and GitHub branch write permissions. **Workflow being committed does not verify a future scheduled run.**