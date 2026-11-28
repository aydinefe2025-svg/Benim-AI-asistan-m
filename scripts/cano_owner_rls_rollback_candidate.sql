-- REVIEW CANDIDATE ONLY; never auto-apply to live. Requires exact pre-cutover
-- snapshot: eight tables RLS disabled, no prior policies, resolver absent.
-- Run in one transaction under an approved rollback decision as table owner.
-- Do not use if baseline differs; preserve unrelated RLS and DML grants.
DROP POLICY cano_owner_scope_v1 ON public.agent_research_drafts;
ALTER TABLE public.agent_research_drafts DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.agent_research_task_events;
ALTER TABLE public.agent_research_task_events DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.agent_research_tasks;
ALTER TABLE public.agent_research_tasks DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.cano_authorized_job_events;
ALTER TABLE public.cano_authorized_job_events DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.cano_authorized_jobs;
ALTER TABLE public.cano_authorized_jobs DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.private_colony_snapshot_revisions;
ALTER TABLE public.private_colony_snapshot_revisions DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.private_colony_snapshots;
ALTER TABLE public.private_colony_snapshots DISABLE ROW LEVEL SECURITY;
DROP POLICY cano_owner_scope_v1 ON public.private_memory_entries;
ALTER TABLE public.private_memory_entries DISABLE ROW LEVEL SECURITY;
DROP FUNCTION public.cano_resolve_local_grant_owner(text,text);
