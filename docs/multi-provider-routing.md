# CANO multi-provider routing

CANO uses its own provider-neutral routing layer (`core/provider_router.py`) and small provider adapters. A user chooses the primary provider; calls are never broadcast to multiple providers for comparison.

## Available backends

- **Ollama local models:** run on the machine hosting CANO. No hosted inference key or provider request is involved.
- **Groq:** available only when `GROQ_API_KEY` is configured. Provider account limits and billing settings apply.
- **Google Gemini:** available only when `GOOGLE_API_KEY` is configured. Google account limits and data terms apply.
- **OpenRouter free pool:** available only when `OPENROUTER_API_KEY` is configured. The adapter pins every request to `openrouter/free`; it cannot select a paid model ID. Free capacity and rate limits are controlled by OpenRouter and the underlying free providers and can change.

`OPENROUTER_API_KEY` is optional. The application does not create an account or key. To keep usage free, configure only a key/account that has no paid balance or paid routing enabled. No key value belongs in source control.

## Failover and privacy

Provider failover is off by default. When the user explicitly enables it, the router tries other available local Ollama models first, then the fixed OpenRouter free pool if configured. It never automatically falls back from/to Groq or Gemini, because the app cannot determine whether those accounts have paid billing enabled. A fallback can send the current prompt and system context to another provider; the UI explains this before opt-in. The router pins the first successful fallback for the rest of that router instance and does not fan a prompt out to several providers.

The model used by OpenRouter may vary as free capacity changes; the app records the returned model identifier for the current response. Rate-limit, network, and account failures remain possible. This design improves choice and resilience; it does not promise uninterrupted or universally free hosted inference.

## Verification limits

Adapter and routing tests mock network calls. They verify free-pool pinning, credential redaction, opt-in failover, and provider selection, but do not prove any external API key, account, quota, model, or live deployment works. Live calls were not made as part of the tests.

