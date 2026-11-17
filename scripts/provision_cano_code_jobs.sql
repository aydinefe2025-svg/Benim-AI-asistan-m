-- CANO web-code executor: new isolated queue, no existing tables modified.
-- Never put connection strings or OIDC secrets in this file.
CREATE TABLE IF NOT EXISTS public.cano_code_jobs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_key text NOT NULL CHECK (owner_key ~ '^oidc_[0-9a-f]{64}$'),
    goal_hash text NOT NULL CHECK (goal_hash ~ '^[0-9a-f]{64}$'),
    goal text NOT NULL CHECK (char_length(goal) BETWEEN 8 AND 1200),
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','pr_open','ci_verified','deployed','blocked')),
    attempts smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 2),
    branch_name text,
    pr_url text,
    commit_sha text,
    ci_run_url text,
    deploy_id text,
    reason_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    UNIQUE(owner_key,goal_hash)
);
ALTER TABLE public.cano_code_jobs ENABLE ROW LEVEL SECURITY;
-- The web app role must never list or insert another signed-in owner's jobs.
CREATE POLICY cano_code_jobs_web_read
    ON public.cano_code_jobs FOR SELECT TO agent_task_app
    USING (owner_key = current_setting('cano.owner_key', true));
CREATE POLICY cano_code_jobs_web_insert
    ON public.cano_code_jobs FOR INSERT TO agent_task_app
    WITH CHECK (owner_key = current_setting('cano.owner_key', true));
-- The autonomous worker uses the existing database owner; the app role is insert/read only.
GRANT SELECT, INSERT ON public.cano_code_jobs TO agent_task_app;
