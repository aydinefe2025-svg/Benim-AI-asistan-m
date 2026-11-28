-- REVIEW CANDIDATE ONLY; never auto-apply to live. Requires exact pre-cutover
-- snapshot: eight tables RLS disabled, no prior policies, approved resolver
-- already installed with its existing ACL. Preserve that resolver and ACL.
-- Run atomically only with approved rollback decision and matching baseline.
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
