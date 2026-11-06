# System verification — 2026-11-06

## Verified working

- **GitHub:** repository file reads and branch/PR APIs are reachable.
- **Kody MCP:** read-only server inventory works; the saved Notion MCP server reports `ready` and connected (77 tools). This verifies the Notion connection, not every Kody capability.
- **Ollama:** local API responds with HTTP 200; `qwen3:8b` is installed.
- **OpenCode:** isolated local wrapper reports v2.2.5 and lists `ollama/qwen3:8b` plus free OpenCode models. No model completion was sent. Its optional background HTTP endpoint on port 4096 is not running.
- **Render:** the free web service is live on branch `fix/sqlite-backup-restore-20261031`. After adding the Gemini secret through Render's masked environment-variable form, deploy `dep-dbmsskmgekts73ecrcjg` for commit `43595bdc2106049bf6b2bc5692bfb1c01a81f550` succeeded and reached **Live**. The Streamlit app loaded successfully; existing CANO data remained present.

## Tests

- Local project test suite: **247 passed**, 1 warning, 46 subtests.
- GitHub Actions status for the deployed commit: no status checks or workflow runs were returned.
- Render build/deploy succeeded; this is separate from the local test run.

## Not verified / remaining limits

- **Groq:** the live app's read-only authenticated model-list check succeeded for the selected model. It sent no prompt and generated no text; inference/quota behavior remains untested.
- **Google Gemini:** the live provider selector now exposes **Google Gemini (Gelişmiş Mod)**. The app's read-only Google connection check succeeded: “Google bağlantısı ve seçili model listede doğrulandı; metin üretilmedi.” This confirms key acceptance and model-list access, not generation quality or quota under load.
- The local research-dashboard provider fallback in this working copy is not part of the deployed Render commit and is not represented as live.
- Render auto-deploy is disabled. Future branch changes require the configured deployment path. The Gemini environment update triggered the successful manual deployment above.
- OpenCode's optional local HTTP background service is inactive, while its CLI and Ollama model listing work.

## Safety

No secret value is included in this report or repository. `GOOGLE_API_KEY` is stored only in Render's masked environment settings. No paid model generation or billing setup was triggered. No stored CANO data was changed. The neutron-star research was left untouched.
