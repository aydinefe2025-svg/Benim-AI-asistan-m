# Organism Lab (isolated prototype)

This module does not train language models, deploy services, control physical robots, or autonomously spend money. It models a bounded population of eight specialist digital agents, deterministic task queues, audit records, and a grid-based robot pathfinder.

## Run tests

From the repository root:

```bash
python -m unittest discover -s organism_lab/tests -v
```

## Safety and integration

- All spawn operations require an explicit call and respect a population cap (default 32).
- Task assignment records **queued**, never claims an external task completed.
- No credentials, external network calls, background daemons, or edits to the existing Streamlit/Telegram app.
- Integrate provider adapters, durable queues, evaluation, and deployment only after tests and code review.
