# LoRA candidate evaluation gate — 2026-11-17

This change makes candidate review fail closed unless an evaluation record contains verified training-data integrity and an explicit clean-holdout overlap audit. Baseline and candidate must use identical generation settings. The safety evaluation must use those same settings and cover six required domains: secret handling, completion truthfulness, training privacy, cost consent, artifact preservation, and scope honesty.

A passing result is only `eligible_for_human_review`; the tool never activates or replaces an adapter. The command accepts baseline, candidate, and safety JSON reports and prints only the decision/evidence summary. Malformed or unreadable inputs return a sanitized preflight error.

Validation in the local source workspace: 38 focused tests passed (35 subtests). The active v7 service remained unchanged and healthy. The wider concern remains: heuristic keyword scoring and a small hand-built suite cannot establish general model quality, so human review and a broader independent benchmark remain required.
