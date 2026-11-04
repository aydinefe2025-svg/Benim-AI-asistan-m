# Connection and test audit — 2026-11-04

## Verified working

- GitHub connector authenticated and can read the repository. PR #71 (optional Google OIDC and owner-scoped PostgreSQL memory) is already merged into `fix/sqlite-backup-restore-20261031`.
- Kody cloud execution works. Its saved MCP server list contains Notion in the ready/connected state. Kody has no saved OAuth integrations.
- Render connector works. Two Free web services are configured with auto-deploy disabled. The latest builds/deploys reported success by Render's control plane.
- Local project virtual environment passes `pip check`, Python syntax compilation, and `git diff --check`.

## Failed check and resolution

- Initial automated test invocation failed before collection because `pytest` was missing from both system Python and the project virtual environment (`No module named pytest`).
- Added `requirements-dev.txt` with the runtime requirements and `pytest>=8.3,<10`, installed it in the project virtual environment, and reran the full suite: **226 tests and 46 subtests passed**.
- PR #107 records the development dependency and this report. The code-bearing head passed GitHub Actions public research checks and core tests on Linux and Windows. The latest commit only corrected this report; no executable code changed afterward.

## Unavailable or not verified

- OpenCode is installed from its official npm package at v2.2.5. `opencode-local.cmd --version` and `debug paths` pass; its runtime data is isolated in `opencode-runtime` because Windows denies writes to the default hidden config directory. It is not yet connected to an inference provider.
- Ollama is still unavailable. The official Windows installer advertises a 1,675,999,728-byte download; the transfer stalled at 1.41 GiB and was stopped before signature verification or execution. The incomplete installer was removed. No model was downloaded. Kody has no saved connections for OpenCode or Ollama.
- System GPU details could not be read in this managed environment. The requested Qwen3:8b model is about 5.2 GB on Ollama; without a verified local runtime and available hardware details, no inference test is claimed.
- Local HTTP probes to both Render service URLs could not reach the endpoints from this environment. Render reports successful deployments, but end-user HTTP health was not independently verified here; recent Render metrics returned no samples.
- Google OIDC credentials are absent from the local workspace; only `.streamlit/secrets.toml.example` exists. The Render connector does not expose secret values, so remote secret presence was not verified. Google MFA completion also remains unverified. OIDC stays opt-in and no deployment was triggered.
- Git CLI fetch failed because this workstation has no Git HTTPS credential available. GitHub MCP access remains operational; PR #107 was created through that authenticated connector.

No paid resource, deployment, credential change, or user-data migration was initiated. Neutron-star research was not touched.
