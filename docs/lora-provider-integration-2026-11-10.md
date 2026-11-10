# Local LoRA provider integration (2026-11-10)

CANO detects the loopback LoRA service at `127.0.0.1:8765` and exposes it as a chat-provider option only when its health response identifies `Qwen/Qwen3-8B` and a valid `candidate-*` adapter. Selecting LoRA routes chat and user-triggered research drafts to the local adapter. The local specialist panel can also run six bounded roles on LoRA.

The provider client applies the deterministic safety gate, bounds input, preserves the newest prompt context, caps responses at 256 KB, and rejects malformed service identities/results. The maintained server at `tools/serve_trained_lora.py` binds only to loopback, loads cached base weights only, and enforces a 32–512 token request budget (256 by default; 96 per specialist role). Specialist outputs remain unverified drafts and cannot access files, shell commands, external services or physical robots.

Start the server from the local training runtime with explicit paths:

```powershell
python -B tools/serve_trained_lora.py --model <local-qwen3-8b-model-directory> --adapter <candidate-adapter-directory> --port 8765
```

Keep the local server running while using LoRA in the local Streamlit app. A hosted Render service cannot reach a loopback endpoint on a personal computer; remote inference needs the model, adapter and compatible GPU runtime provisioned in that environment.

Validation on this machine:
- `python -m unittest discover -s tests -p "test_*.py"`: 279 tests passed.
- `python -m compileall -q app.py core tests tools`: passed.
- A real local LoRA conversation returned `36 / 4 = 9`.
- A real six-role robotics-simulation mission returned all six role outputs with status `draft_unverified`; no physical robot action or independent verification was claimed.

The adapter remains experimental and local. This does not deploy LoRA to Render or prove general answer-quality superiority.
