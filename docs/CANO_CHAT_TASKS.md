# CANO chat task execution

Write `CANO görev: <goal>` in the chat to invoke the bounded team runner. The
goal is limited to 1,200 characters. Other messages keep using the ordinary
assistant response path.

The team creates four ordered model-text stages: planning, research, critique,
and synthesis. Every saved stage is checkpointed to the authenticated owner's
PostgreSQL snapshot before another provider call begins. A completed task is
shown with its task ID and remains marked as a draft awaiting review. The
stages do not execute code, calculations, experiments, or unrestricted web
search. Optional source retrieval remains a separate explicit action in the
command center.

The command requires `GROQ_API_KEY`, the existing colony schema, and a writable
SQLite session. With authenticated owner storage configured, it checks the
owner snapshot before calling the provider and restores that owner's validated
snapshot only into a fresh empty session database. Stale owner snapshots fail
closed. If a provider call or checkpoint fails, completed stages remain saved
and no later stage is called. Retrying the same in-session request resumes the
saved mission; a completed mission ID returns its saved output without another
provider call.

Verification: `python -m unittest discover -s tests` (503 tests, 6 skipped).
