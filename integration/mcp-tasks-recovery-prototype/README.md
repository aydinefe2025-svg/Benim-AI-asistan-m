# Isolated MCP Tasks crash-recovery prototype

This is a test-only prototype of a narrow MCP `2026-07-28` Tasks extension surface over stdio. Its integration harness sends JSON-RPC frames to a separate server process. It uses Node's built-in SQLite, stores before returning a task handle, uses high-entropy task IDs, checks extension negotiation on task calls and task methods, supports `tasks/get` and cancellation, and recovers deterministic in-flight work after process restart.

It is deliberately **not production ready**: the only tool is pure integer addition; it is single-client stdio only, with no account/owner binding, network transport, retention policy, migrations, rate limiting, or side-effecting work. Recovery re-executes only a deterministic operation. A real application needs authenticated owner binding on every task method and an outbox/idempotency design for side effects.

Run with Node 22.13+:

```sh
npm test
```
