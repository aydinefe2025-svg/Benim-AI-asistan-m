# Organism Lab (isolated prototype)

This module does not train language models, deploy services, control physical robots, or autonomously spend money. It models a bounded population of eight specialist digital agents, deterministic task queues, audit records, and a grid-based robot pathfinder.

## Run tests

From the repository root:

```bash
python -m unittest discover -s organism_lab/tests -v
```

## Run an actual bounded research campaign

From the repository root:

```bash
python -m organism_lab.reproduction_study --seeds 30 --steps 100 --model-commentary --output organism_lab_output
```

This runs paired replication/control simulations at five resource levels, retains every per-seed result, calculates paired intervals, and saves JSON, CSV, and a local SQLite record. The optional Qwen commentary uses local Ollama; its structured checks are compared to the computed metrics and contradictions are discarded. The dashboard has the same **Araştırma kampanyasını çalıştır** action. This is a computational study of the simulator, not a biological experiment or a claim that the model learns.

## Safety and integration

- All spawn operations require an explicit call and respect a population cap (default 32).
- Task assignment records **queued**, never claims an external task completed.
- No credentials, external network calls, background daemons, or edits to the existing Streamlit/Telegram app.
- Integrate provider adapters, durable queues, evaluation, and deployment only after tests and code review.

## Verified Streamlit dashboard

The dashboard is isolated from the production Streamlit application. To run it from the repository root:

```bash
python -m pip install 'streamlit>=1.40,<2'
python -m streamlit run organism_lab/dashboard.py
```

Open the URL printed by Streamlit (usually http://localhost:8501). Choose steps, energy and materials, then press **Simülasyonu çalıştır**. Results remain available on subsequent Streamlit reruns; JSON export is provided. This runs an **offline deterministic simulation**, not physical hardware.

The GitHub Actions workflow checks offline tests, Streamlit AppTest interactions, result consistency and an actual Streamlit HTTP health endpoint. **CI success does not imply a public deployment or live LLM credentials.** No new public preview has been deployed. The production Render service uses a separate branch and is intentionally unchanged.


