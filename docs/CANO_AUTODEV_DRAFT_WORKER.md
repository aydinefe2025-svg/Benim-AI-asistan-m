# CANO — bounded draft development worker (P1 pilot)

**Status: source and tests only until PR CI, a configured worker identity and a real owner acceptance run are independently verified.** This is not an unattended safe merge/deploy system and does not replace the normal application.

## What it actually does

1. A verified CANO web owner submits `CANO kod: Düzelt core/cano_development_status.py içinde ...` (a goal of 8–1200 chars). The existing app writes it to the Neon `public.cano_code_jobs` queue.
2. At most one `queued`/`attempts=0` row is atomically claimed using `FOR UPDATE SKIP LOCKED`, independently of Streamlit. The job becomes `running`.
3. A narrowly scoped model generates one full replacement for an **existing** `core/<name>.py` file. The runner never executes generated Python. It rejects changed imports, syntax errors, suspicious added operations and large changes. Sensitive filenames and broad/nontargeted requests are rejected.
4. The worker creates one deterministic GitHub branch and one **draft** pull request, then stores the PR URL, branch and commit SHA in Neon as `pr_open`. Ordinary PR CI can run in its own runner. The worker neither merges nor deploys nor marks CI as passed.
5. Invalid requests and failures get a reason-coded `blocked` receipt. If GitHub may have performed a partial write, `github_write_needs_reconcile` explicitly demands an operator readback instead of retrying blindly.

This first pilot handles one existing low-risk Python file per goal, **not** free-form multi-file coding. User goals are sent to the configured model provider and should contain no secrets or personal information; the private goal is deliberately **not** put into the public PR body.

## Explicitly disabled until configured

- GitHub repository variable `CANO_AUTODEV_ENABLED=true` (default missing/false; set only after checking GitHub Actions usage and provider free-tier limits). Schedule: every four hours, one job maximum per run; manual dispatch also honors enablement.
- GitHub repository variable `CANO_AUTODEV_MODEL`: a currently supported JSON-mode Groq model chosen by the owner. No provider model/cost is silently selected.
- GitHub encrypted Actions secret `GROQ_API_KEY`: a key with limits/budget the owner has approved. Do not copy secrets into docs, source, issues, PRs or chat.
- GitHub encrypted Actions secret `CANO_AUTODEV_DATABASE_URL`: a dedicated narrowly privileged PostgreSQL worker role for the already-existing Neon database, **not** the web app's `agent_task_app` account and **not** a broad administrator credential. It must have only the necessary table permissions and explicit worker RLS rules. Provision under a separate reviewed DBA change; do not weaken the existing web owner's RLS policies.
- The repository Actions setting must permit GitHub Actions to create draft pull requests; if disabled, retain manual PR review/recovery rather than increasing permissions without approval.

For a dedicated worker DB role, review the following *template* with a DBA. This is **not executed by this PR**. Substitute a strong generated password securely, store it only in Actions secrets, and ensure the role cannot read user memory or other production tables. Grant only the named column privileges and row policies on `cano_code_jobs`:

```sql
-- Illustrative reviewed provisioning; never commit or log passwords.
-- CREATE ROLE cano_autodev_worker LOGIN PASSWORD '<private-random-secret>';
GRANT CONNECT ON DATABASE assistant_pg TO cano_autodev_worker;
GRANT USAGE ON SCHEMA public TO cano_autodev_worker;
GRANT SELECT (id,goal,status,attempts,created_at)
  ON public.cano_code_jobs TO cano_autodev_worker;
GRANT UPDATE (status,attempts,started_at,updated_at,
              branch_name,pr_url,commit_sha,reason_code,finished_at)
  ON public.cano_code_jobs TO cano_autodev_worker;
CREATE POLICY cano_autodev_worker_select ON public.cano_code_jobs
  FOR SELECT TO cano_autodev_worker USING (true);
CREATE POLICY cano_autodev_worker_update ON public.cano_code_jobs
  FOR UPDATE TO cano_autodev_worker USING (true) WITH CHECK (true);
```

**Important:** the worker read policy is scoped by *database role and table only*, not by user owner. Review cross-owner task access and the actual credential/grant list before enabling. Prefer dedicated reviewed SECURITY DEFINER RPCs if table-wide worker access is unacceptable.

## Acceptance gates

- `python -m unittest tests.test_cano_autodev_worker -q` passes on Python 3.12 and branch CI passes for the exact PR SHA.
- With the worker **explicitly enabled** and a disposable authorized test job, a real GitHub Actions run reads Neon, writes a *draft* PR, and the same Neon job shows `pr_open` + correct canonical PR and commit SHA. No auto-merge and no production deploy.
- Review changes and new CI separately. A successful synthetic run, source-only PR, or configured Actions workflow **is not** proof of a live autonomous code worker.
- The `running` state is deliberately not auto-reclaimed. A crash may require manual reconciliation; do not requeue until checking for an existing `cano-autodev-<uuid>` branch and draft PR.
- All costs are opt-in. Missing credentials or enable flag fail closed. No secrets or owner goals appear in worker logs.
