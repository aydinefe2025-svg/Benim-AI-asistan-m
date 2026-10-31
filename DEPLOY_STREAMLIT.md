# Deploy the actual Streamlit UI (not Vercel Python Functions)

**Status:** Deployment NOT completed. GitHub unit tests do not verify public availability.
The repository's root `app.py` is a **Streamlit** application using `st.sidebar`, `st.chat_input`, and session state. The connected Vercel project has framework `python` and errors with `PYTHON_ENTRYPOINT_NOT_FOUND`. Do not add a dummy ASGI handler to mask the problem.

## Compatible deployment: Streamlit Community Cloud

Official deployment reference: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy

1. Open https://share.streamlit.io/ and sign into an account with read access to the GitHub repository.
2. Choose **Create app** > **Yup, I have an app**.
3. Set repository: `aydinefe2025-svg/Benim-AI-asistan-m`.
4. Set branch to the *reviewed/deployed* branch. Current candidate for review: `fix/sqlite-backup-restore-20261031` (draft PR #12; **not merged**). After approval/merge, use the intended stable branch instead.
5. Set main file path `app.py`. Select Python 3.12 in **Advanced settings**. Root `requirements.txt` already lists `streamlit`, `google-genai`, `groq`, `requests`.
6. Add the following variable **names** under **Advanced settings > Secrets** and enter the real values privately in the host UI (not GitHub, Notion, logs, or chat):

   ```toml
   # Configure one or both, only in the hosting platform's Secrets UI:
   # GOOGLE_API_KEY = "<configured-privately>"
   # GROQ_API_KEY = "<configured-privately>"
   ```

   The updated app requires **at least one** key, not both. It offers only the configured provider(s) in the sidebar. Without either key, it stops with a safe configuration message. This behavior is tested in [GitHub Actions run #41196912982](https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/actions/runs/41196912982), 86/86 unit tests. Acquire and configure only the keys you are permitted to use. Never commit a `secrets.toml` file.
7. Deploy, open the resulting actual `streamlit.app` URL, verify sidebar and chat input work, and try a controlled Groq/Google request. Keep any API error details and personal keys private.
8. Confirm that an ordinary prompt gives the right model response; then check a location-specific weather request and a named-entity instant-answer query. The DuckDuckGo *Instant Answer API* is not a full web search engine.
9. Record only a **verified** working URL and deployment status in GitHub issue #7. Until then, deployment remains *unverified*.

## Vercel mismatch

GitHub issue: https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/7

Actual Vercel deployment `dpl_8kF16t6wwZBQbubJxaQyUALuXTXi` failed with `PYTHON_ENTRYPOINT_NOT_FOUND`; the error says the root `app.py` has no top-level `app`, `application`, or `handler`. A Streamlit app uses a long-running server process, which this Vercel Python Functions entrypoint does not provide. If the Vercel integration continues to auto-build every branch push, choose intentionally whether to disconnect/disable that build after confirming no other app depends on the project. **No account/project settings were changed by this guide.**

## Current limits and security

- A passing GitHub CI run is **not** a live Streamlit smoke test.
- Cloud deployment requires host authentication and secrets set within that account; no hosting or paid plan may be assumed active.
- SQLite tests use temporary databases. A managed persistent archive needs a separate storage/backup and permissions plan; Streamlit Community Cloud's ephemeral runtime must not be mistaken for durable archive storage.
- The app includes a provider-independent identity note and avoids showing raw provider exception text to visitors, but further integration tests with real credentials and rate limits are still needed.
