# Organism Lab cloud service

This service stores authenticated user data in the existing Neon PostgreSQL
project. It does not modify the production assistant or migrate existing data.

## Runtime configuration

Set these as Render environment secrets on the isolated Organism Lab service:

- `DATABASE_URL`: a dedicated least-privilege database role, not the Neon owner.
- `ORGANISM_LAB_OWNER_EMAIL`: the sole allowed, verified Google account.
- `ORGANISM_LAB_OWNER_KEY_SECRET`: stable random value with at least 32 bytes.
- `LAB_OIDC_REDIRECT_URI`: `https://organism-lab-cloud-demo.onrender.com/oauth2callback`
- `LAB_OIDC_COOKIE_SECRET`: stable random value with at least 32 bytes.
- `LAB_OIDC_CLIENT_ID`, `LAB_OIDC_CLIENT_SECRET`: Google OAuth web client.
- `LAB_OIDC_METADATA_URL`: `https://accounts.google.com/.well-known/openid-configuration`
- `GROQ_API_KEY`: freshly rotated Groq secret; optional until chat is needed.
- `ORGANISM_LAB_CLOUD_MODE=1`.

The startup bootstrap writes only the OIDC TOML into a private temporary file
and configures Streamlit to read it. No secret is committed or logged. The app
fails closed while identity, database, or owner configuration is incomplete.

## Durable storage and recovery

The application does not run DDL at startup. A reviewed migration creates
`public.organism_lab_records`; the runtime role needs only SELECT, INSERT,
UPDATE and DELETE on that table. Notes, research files, chat turns, simulation
results, and experiment outputs are snapshotted per verified owner. Snapshot
writes use a SHA-256 integrity check and compare-and-swap to prevent an older
concurrent session from overwriting a newer archive. The dashboard supports
private archive download and validated restore; restore paths reject traversal,
links, and oversized files.

Neon free tier is durable within published quotas, not an SLA: 1 GB storage,
100 compute-hours per project/month, 5 GB egress, and up to 6 hours of instant
restore history at the time of verification. Download independent backups
regularly. Paid plans, long retention, or higher capacity require explicit
approval. No old session data is migrated automatically.

## Render settings

- Build: `pip install -r organism_lab_cloud/requirements.txt`
- Start: `python organism_lab_cloud/bootstrap.py`
- Region/plan: Frankfurt / Free
- Auto deploy: disabled

All colony and evolution results are digital simulations, not biological or
physical-system control. Assistant conversations do not train model weights.

The on-demand colony resilience study compares bounded open-broadcast and
segmented/validated message-passing simulations under one injected bad-message
fault. It records paired deterministic trials and versioned JSON output. This
abstract scenario is not a penetration test, production security control, or
guarantee that real agents/networks will resist attacks.

## Bounded automated discovery

`.github/workflows/organism-lab-discovery.yml` runs a weekly simulation sweep
and can also be started manually from GitHub Actions. It screens five bounded
mutation rates, selects at most one positive candidate, and tests it against a
zero-mutation control using separate, held-out random seeds. The runner
recomputes the archived report before saving it under
`research_reports/organism-lab-discoveries/`. The report records either a
simulation-only repeat, a candidate that did not repeat, or no positive
screening candidate; none is labeled a biological or real-world discovery.

Pull request checks continue to run the Organism Lab regression suite. The
hourly CANO job is proposal-only and does not start agents or model calls.
Scheduled jobs run on GitHub-hosted runners and require no Render worker or
provider API key. Their output is public repository history, so archive only
non-sensitive deterministic measurements and never include user chat/data.

