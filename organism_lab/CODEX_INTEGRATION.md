# Codex collaboration contract

This module is isolated in `organism_lab/`. Codex can integrate it without
rewriting the existing Streamlit or Telegram applications.

- `Colony.initialize()`: creates eight specialist roles.
- `grow_on_demand(colony, role, queued_tasks=n)`: bounded same-role replication.
- `execute_task(colony, role, task, executor, verifier)`: executes a task using
  explicitly injected functions and records checked/failed status. A check is
  not source verification unless the injected verifier independently validates
  provenance and claim-to-source evidence.
- `World(seed=..., capacity=..., resources=...)`: simulated digital organism
  reproduction, inheritance and resource competition.
- `compare_control(...)`: experiment vs non-replicating baseline.

## Integration gate

1. Keep secrets server-side. Never log prompts with secrets or provider keys.
2. Use real task executors and independent evidence checks before reporting success.
3. Run `python -m unittest discover -s organism_lab/tests -v`.
4. Review GitHub PR #15 and reconcile with Codex's branches before merging.
5. Do not confuse digital organism births with deployed AI agents or physical robots.
6. No unbounded spawning, self-deployment, spending or background processes.
