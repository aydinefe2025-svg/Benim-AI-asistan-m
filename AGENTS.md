# CANO — Repository-Wide Agent Instructions

These instructions apply to Codex and other coding agents reading this repository. They do not grant access outside this repository or replace user/system policies.

**Mandatory first read**: `docs/CANO_CONTINUOUS_PROGRESS_PROTOCOL.md` and `docs/CANO_MASTER_REQUIREMENTS_2026-11-04.md`, plus the latest applicable GitHub Issue #95, related PR/CI, and project-specific Notion evidence record.

## Cross-agent CANO recovery handoff — read before reopening tasks

For CANO Render PostgreSQL 18 backup, restore-target safety, owner-local preflight, or disaster-recovery automation, **first read the current [Issue #440](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/440)** and parent [Issue #95](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/95). Check the most recent production-source commit and PR status. #440 is the shared **Codex ↔ ChatGPT ↔ GitHub** task checkpoint; it contains completed work, exact CI evidence, outstanding real-data acceptance, and access blockers.

Do not recreate a completed restore source guard (#448 merged; earlier drafts #424/#433 superseded), Render rescue operator CLI (#435/#438), offsite readback (#441), Windows preflight (#443), or PG18 client guard (#446/#459) without identifying a *new* source-backed defect. Do not mistake a merged source commit or synthetic CI for a live Render deployment or a real offsite restore. If Codex Cloud lacks a connected environment, say so explicitly; a GitHub issue mention is **not** proof of an active agent session. Check updated issue/PR status each session rather than assuming this dated list remains current.

## Standing objective: measurable progress without repeated user prompting
On each authorized work session:
1. Recover the current topic's canonical state and prior evidence. Resume the last open acceptance criterion; do not restart a completed study or duplicate another agent's PR.
2. Select one highest-value unblocked task, preferably implement or run a real reproducible test rather than only describe a plan.
3. If blocked, diagnose; document precise blocker; pursue a safe alternate unblocked task in the same approved scope.
4. Use focused tests, regression checks, and, where appropriate, independent CI/live readback. Never conflate code merged with code deployed, simulation with physical realization, or data model with a verified scientific finding.
5. Store only verified artifacts, run receipts, hashes and a next-step checkpoint in the existing topic's GitHub/Notion/Library record. Verify the write by reading back. If the connection fails, report unsaved status without claiming archival success.
6. Keep output brief: one genuine improvement, evidence, current limitation, next actionable step. No repeated summary-only loops and no unsupported “100%” claims.

## Project boundaries
- Keep CANO production, the isolated digital organism/robot CAD lab, global discovery, opportunities, robotics/cellular models, historical technology, and neutron-star research in distinct task keys and archive paths.
- Global discovery and opportunities automations intentionally exclude J0740/EOS; do **not** silently widen them. Dedicated neutron-star work uses its own A01.01.50 / A01.01.51 evidence.
- Default to free resources, finite computation, explicit bounds, reliable shutdown, source attribution, and safe recovery. No destructive migrations, production redeploy without current data safety, unauthorized third-party access, autonomous uncontrolled replication, credential exposure, or unapproved charges.
- For all new design/experiment proposals (including self-build), distinguish design/code, simulated test, manufactured hardware, and verified autonomous operation.

The repo's `AGENTS.md` guides agents who actually read its checkout. It does **not** magically modify all existing ChatGPT chats, remote Codex sessions or trigger its own background tasks. Scheduled ChatGPT tasks have separate prompts.
