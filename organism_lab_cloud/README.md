# Organism Lab cloud demonstration

This is a separately deployed copy of the local deterministic simulation app.
It does not alter the main assistant or the existing production Render service.

Render settings for the isolated test service:

- Build: `pip install -r organism_lab_cloud/requirements.txt`
- Start: `streamlit run organism_lab_cloud/organism_lab/dashboard.py --server.address 0.0.0.0 --server.port $PORT --server.headless true`
- Environment: `ORGANISM_LAB_CLOUD_MODE=1`
- Region/plan: Frankfurt / Free
- Auto deploy: disabled

The hosted demo runs deterministic simulations and explicit OpenAlex lookups.
It cannot reach the user's Ollama server or local LoRA adapter. If a Groq key is
added through Render's secret manager, explicit chat prompts and selected saved
notes are sent to Groq. No key belongs in this repository.

Cloud data is isolated to an unpredictable Streamlit session directory under
temporary storage. Render restarts and deployments can erase it. The demo has
no login and no durable archive, so it must not receive sensitive notes or be
presented as a production data service. Download reports that need to be kept.
Production use requires authenticated users, durable per-user storage, backup
and restore evidence, and tested access controls first.

All colony, organism, and evolution results are digital simulations. They do
not create or control biological organisms, physical robots, or model weights.
