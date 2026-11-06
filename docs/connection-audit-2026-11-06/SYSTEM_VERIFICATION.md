# System verification — 2026-11-06

## Verified working

- **GitHub:** repository file reads and branch/PR APIs are reachable.
- **Kody MCP:** read-only server inventory works; the saved Notion MCP server reports `ready` and connected (77 tools). This verifies the Notion connection, not every Kody capability.
- **Ollama:** local API responds with HTTP 200; `qwen3:8b` is installed.
- **OpenCode:** isolated local wrapper reports v2.2.5 and lists `ollama/qwen3:8b` plus free OpenCode models. No model completion was sent. Its optional background HTTP endpoint on port 4096 is not running.
- **Render:** the service build and deploy for commit `b7edabec456a4eebe9a1697e9edc11e17fbb089d` succeeded (deploy `dep-dbmpji6gekts73e5jijg`). The live Streamlit app loaded after the rollout and showed the CANO command center, 11 specialists, and 2 saved prior team tasks. No task, specialist, or saved data was changed.

## Tests

- Local project test suite: **247 passed**, 1 warning, 46 subtests.
- GitHub Actions status for the deployed commit: no status checks or workflow runs were returned.
- Render build/deploy succeeded; this is separate from the local test run.

## Not verified / remaining limits

- **Groq:** the live app's read-only authenticated model-list check succeeded for the selected model. It sent no prompt and generated no text; inference/quota behavior remains untested.
- **Google Gemini:** the live provider selector exposes only Groq, so Gemini is not configured/available in this production app. No Google key value was inspected.
- The local research-dashboard provider fallback in this working copy is not part of the deployed Render commit and is not represented as live.
- Render auto-deploy is disabled. Future branch changes require the configured deployment path; nothing was deployed as part of this audit.
- OpenCode's optional local HTTP background service is inactive, while its CLI and Ollama model listing work.

## Safety

No API keys or secret values were read or recorded. No paid model generation was triggered. No Render variables, deployment settings, or stored CANO data were changed. The neutron-star research was left untouched.

