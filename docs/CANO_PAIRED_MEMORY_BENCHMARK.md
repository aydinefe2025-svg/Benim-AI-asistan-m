# CANO paired colony-memory benchmark

Use this helper to compare the same agent with accepted lessons disabled and enabled:

```python
result = run_colony_memory_benchmark(
    colony,
    agent_id,
    labeled_cases,
    client=client,
    model="configured-model",
    source_refs=("dataset:reviewed-v1",),
    safety_pass=False,
)
```

The client must expose `chat(model, system, prompt)`. The caller chooses and supplies the client; the helper does not provision a provider. It executes each case twice for each condition, so an N-case suite makes 4N model calls. The integrated helper allows at most 10 cases (40 calls). A paid client can incur charges if the caller runs the helper.

Use a held-out, human-labeled task set with stable case IDs and exact expected answers. Record the dataset version and source references. Start with a deterministic local fake client to verify wiring without provider calls. For any real run, review the task labels and approve the exact model/provider and expected call count before execution.

Interpret exact-match scores as a narrow task-set measurement, not general intelligence or scientific correctness. Inspect every regressed case before considering a lesson reusable. The result includes the per-case improved/regressed IDs, repeatability flags, and benchmark digest, but omits prompts and model outputs. Accepted feedback remains retrieval memory; this does not train model weights or automatically promote a candidate.

Do not mark the learning-benefit acceptance gate complete until a representative labeled suite has been run and regression results reviewed.

Task-specific retrieval now checks meaningful word overlap between the requested task, the feedback task label and the lesson. Use `*` as the feedback task label only when a lesson should apply to every task. Unrelated accepted lessons are omitted; this is deterministic keyword matching, not semantic search. Matching scans at most the 500 newest accepted lessons and returns at most the configured limit. Include task-specific cases in the labeled benchmark and inspect both improved and regressed cases.

