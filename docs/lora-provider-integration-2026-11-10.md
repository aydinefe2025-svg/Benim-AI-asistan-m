# Local LoRA provider integration (2026-11-10)

CANO now detects the loopback LoRA service at `127.0.0.1:8765` and exposes it as the first chat-provider option only when its health response identifies `Qwen/Qwen3-8B` and a syntactically valid `candidate-*` adapter. Selecting it routes both ordinary chat and the user-triggered research-draft callback through that provider. The Streamlit app displays the active candidate ID.

The provider client only calls the fixed loopback address, applies the existing deterministic safety gate, bounds input to 100,000 characters, clips the transmitted prompt to the server's 12,000-character limit while preserving the newest end, caps responses at 256 KB, and rejects malformed service identities/results. The local inference server still bounds generation at 512 tokens. Provider failover remains off unless the existing UI opt-in is enabled. No model, credentials, external network, deployment, or user data was changed.

Validation on this machine:
- `python -m unittest discover -s tests -p "test_*.py"`: 277 tests passed.
- `python -m compileall -q app.py core tests`: passed.
- Streamlit `AppTest`: LoRA was the selected chat model; a real local conversation went through provider `LoRA (Yerel · Qwen3-8B deneysel)` and answered `36 / 4 = 9`.

The adapter is still experimental and only local. This change does not give LoRA direct filesystem, GitHub, Render, or arbitrary shell access, and does not deploy the model to Render. Existing app tools can use it for text generation/drafts; actions remain within the app's explicit handlers.

