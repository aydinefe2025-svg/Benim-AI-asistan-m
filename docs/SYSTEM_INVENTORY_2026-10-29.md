# System inventory — 2026-10-29

This file records only states observed through connected tools in this session. It does not claim to inspect the user's local computer.

## Connected systems checked

| System | Observed state | Evidence / boundary |
|---|---|---|
| GitHub | One repository returned by the connected GitHub account listing: `aydinefe2025-svg/Benim-AI-asistan-m`; admin/push permissions are present. | GitHub repository listing. This does not prove no other repositories exist outside the current connection. |
| GitHub PR #2 | Open, mergeable, not merged; branch `feature/buyuk-sistem-core`; 13 files changed, 782 additions at last inspection. | https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/pull/2 |
| GitHub Actions | Core unit-test workflow succeeded on the latest inspected head `b304c96e483848d301bb41ec5b4101f08b12797e`, run `40922383532`. | `unittest` step completed successfully. This is CI/Linux evidence, not Windows/local verification. |
| Vercel | Existing project `benim-ai-asistan-m` exists, but both main and feature deployments are in ERROR. | Exact code: `PYTHON_ENTRYPOINT_NOT_FOUND`: root `app.py` is Streamlit and exports no top-level `app`, `application`, or `handler`. |
| Vercel environment variables | Filter returned no environment variables and no hidden production env count. | The existing Streamlit app expects `GOOGLE_API_KEY` and `GROQ_API_KEY`; these were not present in the Vercel project's env inventory. Values were not decrypted or exposed. |
| Notion | Main discovery archive, system design, A01.01.50 gravity-wave page, A01.01.51 neutron-star pages, multi-agent protocol, and J0740 audit pages are accessible by page search/fetch. | Notion page reads are available. Connected-source search across Google Drive/GitHub/mail via Notion connector is blocked by Business-plan entitlement; this limitation must not be confused with Notion page search. |
| ChatGPT Library | 75 items returned by recursive Library listing, including Ruflo starter ZIP, J0740 validation package, research recovery bundle, and historical research summaries. | This is the connected Library listing, not a scan of all external cloud drives or local folders. |
| Supabase / Neon | Supabase returned zero projects; Neon returned an empty project list. | No connected database project is available from these two connectors at this time. This does not rule out other storage providers. |
| Local computer / Ollama | Not inspected or executed in this session. | Prior records report Windows, Python, VS Code, Ollama 0.40.10 and qwen3:8b, but current live connectivity has not been demonstrated. |

## Deployment decision

Do not claim the current Vercel site is a working AI system. The project is configured as Python but its root entrypoint is a Streamlit script, which is incompatible with the configured Vercel Python function entrypoint. In addition, no Vercel environment variables were returned and no connected Supabase/Neon database is available. Fixing only the entrypoint would not provide secure model credentials or durable storage.

Safe next architecture decision:
1. Keep the existing Streamlit app separate from any Vercel API entrypoint until a real deployment architecture is selected.
2. Keep SQLite for the local dashboard only; do not claim serverless SQLite is durable across Vercel invocations.
3. Select/configure an authorized persistent database and server-side model credentials before calling a hosted version fully functional.
4. Continue using connected GitHub and Notion as the current code/evidence archive, with explicit evidence and verification status.

## Library recovery correction

The 2026-10-29 recursive Library inventory found `Research Library Recovery 2026-10-29/04_HISTORICAL_RESEARCH_FILES_01-12.md`, `07_MEROE_NAVIGATION_BIRUNI_FILE_09.md`, `06_AGARIA_MAYA_KHIPU_FILE_08.md`, and the recovery manifest. Therefore:
- The second historical series' File 09 exists as a recovered summary document.
- File 10 (Cezerî) and first-series items 10 (Wootz) and 11 (Guangzhou metallurgy) are listed in the historical index, but separate full standalone reports were not established by the listing.
- The first 12-topic series and the later series have different numbering. Never infer absence from Notion search alone, and never collapse the two numbering schemes.

## Existing local coordinator artifact

Library contains `ruflo_local_coordinator_starter.zip`. Its README and source show a local Ollama role-based workflow (planner, skeptic, synthesis) that saves Markdown reports. It does not perform web browsing or automatic Notion archiving, and if all roles use qwen3:8b it is not independent multi-model consensus. The package is a starter artifact; no live Ollama call was run in this session.
