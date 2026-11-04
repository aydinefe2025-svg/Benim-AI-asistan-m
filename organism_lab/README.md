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

This runs paired instruction-executing genome/control simulations at five resource levels. A genome must execute `COPY_REST` then `DIVIDE`; inherited opcodes can mutate, and the control uses the same genome with division disabled. The run retains every per-seed result, calculates paired intervals, and saves JSON, CSV, and a local SQLite record. Optional Qwen checks use local Ollama; its structured checks are compared with computed metrics and contradictions are discarded. Commentary is not evidence or source verification. The dashboard has the same **Araştırma kampanyasını çalıştır** action. This is a computational study of this deliberately small virtual machine, not a biological experiment or a claim that the model learns.

## Verifiable genome study replay

The genome campaign now **re-opens all three persisted formats** (JSON,
per-seed CSV, SQLite) and re-runs the deterministic experiment with its saved
parameters before reporting success. It rejects missing, altered or mismatched
files and returns a receipt with the JSON SHA-256 digest. A separate process
can re-check the archive without the original Streamlit session:

```bash
python -m organism_lab.reproduction_study --seeds 30 --steps 100 --output organism_lab_output
python -m organism_lab.study_verifier organism_lab_output/STUDY_ID.json
```

Replace STUDY_ID with the UUID filename printed by the first command. Every
new CLI campaign saves a separate study; repeat runs are not automatically
deduplicated. The Streamlit dashboard marks a campaign **saved** only after
readback and independent recomputation succeed. CI deliberately tampers with
stored data and confirms that verification fails. GitHub artifacts expire
after 30 days, requiring an additional persistent backup.

The feature branch is isolated from the production CANO service. Green CI
tests verify the deterministic simulator and local persistence only, not
public accessibility, autonomous model learning, living cells or physical
robotics. Production deployment needs separate verification.

## Restartable digital genome state

A local, single-writer digital genome checkpoint can survive a Python process
restart. It stores a SHA-256 digest and the complete simulated population
state; loading verifies the digest and **replays all ticks** from the stored
seed. Resume by target tick (rather than by adding steps), so repeating the
same command does not duplicate a simulated operation:

```bash
python -m organism_lab.genome_checkpoint init organism_state.json --seed 17 --target-tick 35
python -m organism_lab.genome_checkpoint verify organism_state.json
python -m organism_lab.genome_checkpoint advance organism_state.json --target-tick 120
python -m organism_lab.genome_checkpoint verify organism_state.json
```

The checkpoint tool refuses to overwrite an existing file on initialization,
rejects backward moves, and limits execution to 10,000 ticks. Checkpoint
persistence is not a continuously running background worker or multi-server
leader election. For simultaneous writers, add a proper transactional lock
before any service deployment.

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
