-- Candidate migration: do not apply automatically or as a runtime role.
-- Install atomically as the trusted table owner with an approved role grant.
-- Do not grant to PUBLIC. Owner must be able to resolve rows under RLS.
CREATE FUNCTION public.cano_resolve_local_grant_owner(p_job_id text, p_worker text)
RETURNS text
LANGUAGE sql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $resolver$
    SELECT CASE WHEN count(*) = 1 THEN min(j.owner_key) ELSE NULL END
    FROM public.cano_authorized_jobs AS j
    WHERE p_job_id ~ '^[0-9a-f]{32}$'
      AND p_worker ~ '^local-http-(ready|taken):[0-9a-f]{64}$'
      AND j.id = p_job_id
      AND j.worker_id = p_worker
      AND j.state = 'running'
      AND j.lease_token IS NOT NULL
      AND j.lease_until > EXTRACT(EPOCH FROM pg_catalog.clock_timestamp())
$resolver$;
REVOKE ALL ON FUNCTION public.cano_resolve_local_grant_owner(text,text) FROM PUBLIC;
-- Grant EXECUTE only to the reviewed application capability runtime role.
