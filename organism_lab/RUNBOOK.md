# Run the organism laboratory

From repository root, no third-party packages or API keys required:

```bash
python -m unittest discover -s organism_lab/tests -v
python -m organism_lab.runner --seed 7 --steps 30 --output experiment.json
```

The JSON contains independent digital evolution and shared-budget virtual robot
experiments. The two models are **not** coupled at the individual-organism level.
For a CSV time series, import `organism_lab.experiments.to_csv` and call it on
`run_experiment(...)`. Treat outputs as simulated data, not real-world results.

Run a paired resource study with a non-replicating control:

```bash
python -m organism_lab.reproduction_study --seeds 30 --steps 100 --model-commentary --output organism_lab_output
```

This writes raw per-seed rows to JSON and CSV and appends a study record to
`organism_lab_output/research_studies.sqlite3`. Qwen commentary is optional and
local; the code rejects structured metric checks that conflict with computed
intervals. It is a bounded simulation campaign, not persistent background
learning or external-source research.

Codex integration: import `organism_lab.runner.report` in a separate UI view.
Do not merge PR #15 until the branch CI and code review pass. Keep secrets and
production deployment outside the offline experiment runner.


