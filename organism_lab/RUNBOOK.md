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

Codex integration: import `organism_lab.runner.report` in a separate UI view.
Do not merge PR #15 until the branch CI and code review pass. Keep secrets and
production deployment outside the offline experiment runner.
