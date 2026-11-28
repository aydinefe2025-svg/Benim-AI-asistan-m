-- Review candidate; run in one transaction only after approved protected key provisioning and app deployment.
DO $$ BEGIN
 IF (SELECT count(*) FROM cano_context_proof.signing_key) <> 6 THEN RAISE EXCEPTION 'Signed owner key registry incomplete'; END IF;
 IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname IN ('agent_research_drafts','agent_research_task_events','agent_research_tasks','cano_authorized_job_events','cano_authorized_jobs','private_colony_snapshot_revisions','private_colony_snapshots','private_memory_entries') AND (c.relrowsecurity OR c.relforcerowsecurity)) THEN RAISE EXCEPTION 'Unexpected pre-cutover RLS state'; END IF;
END $$;
-- REVIEW CANDIDATE ONLY. Do not execute on production before deployed-code,
-- role-binding, backup, independent security review and rollback acceptance.
-- Existing DML grants are deliberately unchanged. Owner bypass is unchanged.
-- Apply atomically as table owner. Resolver must already be installed.
CREATE POLICY cano_owner_scope_v1 ON public.agent_research_drafts
    FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.agent_research_drafts ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.agent_research_task_events
    FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.agent_research_task_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.agent_research_tasks
    FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.agent_research_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.cano_authorized_job_events
    FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime, organism_lab_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.cano_authorized_job_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.cano_authorized_jobs
    FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime, organism_lab_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.cano_authorized_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.private_colony_snapshot_revisions
    FOR ALL TO cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, organism_lab_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.private_colony_snapshot_revisions ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.private_colony_snapshots
    FOR ALL TO cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.private_colony_snapshots ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_owner_scope_v1 ON public.private_memory_entries
    FOR ALL TO cano_runtime_rw, cano_snapshot_runtime, memory_runtime_app
    USING (owner_key = nullif(current_setting('cano.owner_key', true), ''))
    WITH CHECK (owner_key = nullif(current_setting('cano.owner_key', true), ''));
ALTER TABLE public.private_memory_entries ENABLE ROW LEVEL SECURITY;
-- The resolver is needed by the authenticated task application capability path.
GRANT EXECUTE ON FUNCTION public.cano_resolve_local_grant_owner(text,text) TO agent_task_app;

CREATE POLICY cano_owner_proof_v1 ON public.agent_research_drafts AS RESTRICTIVE FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.agent_research_task_events AS RESTRICTIVE FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.agent_research_tasks AS RESTRICTIVE FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.cano_authorized_job_events AS RESTRICTIVE FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime, organism_lab_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.cano_authorized_jobs AS RESTRICTIVE FOR ALL TO agent_task_app, cano_runtime_rw, cano_snapshot_runtime, organism_lab_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.private_colony_snapshot_revisions AS RESTRICTIVE FOR ALL TO cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, organism_lab_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.private_colony_snapshots AS RESTRICTIVE FOR ALL TO cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
CREATE POLICY cano_owner_proof_v1 ON public.private_memory_entries AS RESTRICTIVE FOR ALL TO cano_runtime_rw, cano_snapshot_runtime, memory_runtime_app
 USING (owner_key=(SELECT cano_context_proof.verified_owner())) WITH CHECK (owner_key=(SELECT cano_context_proof.verified_owner()));
