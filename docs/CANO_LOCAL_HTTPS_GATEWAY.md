# CANO local HTTPS worker — deployment gate

The existing Streamlit file-transfer feature remains available. Network grant
issuance defaults to disabled. No production startup or environment change is
made by this PR.

- The authenticated owner UI may issue one random, expiring grant only after
  explicit confirmation. The existing PostgreSQL lease and attempt budget
  remain authoritative. Revocation is available even while issuance is off.
- The local worker reads the grant through a hidden terminal prompt, performs
  one loopback Ollama inference, records the attempt and submits the matching
  result. Uncertain responses never trigger another model call.
- The worker command is `python -m core.local_grant_worker --origin https://TRUSTED-GATEWAY --approved`.
  The operator must use the actual trusted HTTPS origin, never an arbitrary
  origin from a ticket. Do not put grant values in command lines, logs or files.
- The WSGI entry point is `core.local_grant_gateway:from_environment()`.
  It is not a public listener. Use a production WSGI server with one process
  (global rate bound is per process), bounded threads and deadlines, behind
  an HTTPS proxy that strips client-supplied forwarded headers and sets the
  trusted WSGI HTTPS scheme. Route only POST /v1/local-task/take and
  /v1/local-task/finish to it; preserve existing Streamlit routes, WebSocket
  upgrade and OIDC callback. Bound request bodies to 65536 bytes, headers,
  request duration and connections at the proxy/server. Do not log
  Authorization, request bodies, or database credentials.
- Gateway and owner UI both require CANO_LOCAL_GRANT_ENABLED=1 and the existing
  server-side AGENT_TASK_DATABASE_URL. Do not copy that credential to Windows.
  Until the gateway is actually deployed and HTTPS/negative/health tests pass,
  leave the flag unset. Never expose Ollama or the WSGI listener directly.
- Live acceptance: independently verify public TLS, wrong grant denied,
  plaintext denied, existing Streamlit health and OIDC, one owner-approved
  harmless task from Windows, one attempt, exact draft readback and consumed
  grant; also verify revoke and server restart behavior. On error disable
  issuance, reconcile outstanding grants, and preserve the existing queue.

The current Render startup is Streamlit-only. The Render connector does not
offer a service startup update action; a trusted deployment configuration and
authenticated owner session are still needed. No additional paid service is
required or authorized by this document.
