# CANO digital checkpoint v2 — opt-in calendar bridge

This is a **finite digital-simulation** migration candidate. It does not create
living organisms, automatic model learning, or unlimited independent workers.
The default calendar remains v1 unless an operator **explicitly migrates** an
existing checkpoint with its independently verified/pinned v1 SHA-256.

## Safeguards

- v1 anchor is embedded unchanged and independently replayed, including its
  complete historical organism list, lineage, resource settings, and SHA.
- bounded v2 replays apply an experimental maintenance-first energy policy after
  the anchor; history up to that tick is never recomputed under the new policy.
- shared calendar and checkpoint file locks protect cross-process writers;
  atomic writes and readback prevent partial daily/checkpoint publication.
- same-day retry produces no new birth records; conflicting or forged daily
  reports fail closed. v1 history remains a v1 report; no overwrite.
- both existing calendar and watchdog entrypoints can dispatch to v2 **only
  after explicit migration**; existing v1 behavior remains the default.
- start only in an **isolated copy** of the state directory. Do not migrate the
  authoritative state branch or deploy this while CI, rollback, and published
  observatory support remain unverified.

## Reproduce without touching production

From repository root:

```bash
python -m unittest organism_lab.tests.test_versioned_calendar -v
```

1. Copy the original v1 `genome-state.json` into an isolated directory.
2. Obtain its verified `sha256` from an independent canonical readback.
3. Explicitly migrate only that copy:

```bash
python -m organism_lab.versioned_calendar migrate --state-dir PATH --expected-anchor-sha VERIFIED_SHA
python -m organism_lab.versioned_calendar run-day --state-dir PATH --day 2026-11-27 --expected-anchor-sha VERIFIED_SHA
python -m organism_lab.versioned_calendar inspect-day --state-dir PATH --day 2026-11-27
```

Never invent the pin, never run a future date before earlier scheduled dates
without understanding the audit implications, and never use live branch paths
for initial experiments. The v1 source fixture used in tests is the 2026-11-26
160-tick checkpoint, not a generated mock.

## Remaining scientific acceptance

This code validates **state integrity and mortality-policy accounting only**.
It does not establish environment-dependent heritable adaptation, unseen-task
transfer, or true biological/physical life. Independent controls, held-out
fitness, long-running failure recovery, UI compatibility, and external CI are
necessary before any production switch.
