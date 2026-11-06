# Free local Ollama path for CANO

When the app runs on a computer that has Ollama installed and a local model available, the CANO command center can use that model for user-triggered drafts.

## Run locally

1. Start Ollama and make sure `ollama list` shows a model.
2. Start the Streamlit app from the project directory. `OLLAMA_URL` defaults to `http://127.0.0.1:11434`; override it only for a trusted local endpoint.
3. Select `Ollama (Yerel)` in the model picker and use the CANO command center normally.

The local path makes synchronous inference requests to the configured Ollama endpoint. It applies a 256-token output cap per stage and disables Qwen3 thinking mode to avoid empty short responses. Results remain drafts for human review; they do not train model weights, change source files, spawn processes, or deploy code. The six-role mission workflow also refuses neutron-star topics.

## Deployment boundary

A Render service's `127.0.0.1` is inside its own container. It cannot reach Ollama running on the user's computer. This path therefore works only when the app and Ollama run in the same trusted local environment. No public tunnel or paid provider is configured by this feature.
