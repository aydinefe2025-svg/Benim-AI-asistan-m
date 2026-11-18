# LoRA candidate evaluation gate — 2026-11-18

This change makes candidate review fail closed unless evaluation records include verified training-data integrity and an explicit clean-holdout overlap audit. Baseline and candidate must use identical generation settings. The safety evaluation must use the same generation settings and cover six domains: secret handling, completion truthfulness, training privacy, cost consent, artifact preservation, and scope honesty.

A passing result is only `eligible_for_human_review`; the tool never activates or replaces an adapter. The CLI accepts baseline, candidate, and safety JSON reports. Malformed inputs return a sanitized preflight error.

Local verification: 38 focused tests passed (including 35 subtests). The active v7 service remained unchanged and healthy. The existing LoRA candidate R6 was rejected: its raw score tied the baseline (14/18) and only 3/6 safety cases passed. General model quality still requires a broader independent benchmark and human review.
