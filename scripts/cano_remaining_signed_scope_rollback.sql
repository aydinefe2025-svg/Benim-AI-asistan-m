-- Candidate rollback. Preserve original RLS and existing policies.
DROP POLICY cano_code_jobs_signed_scope_v1 ON public.cano_code_jobs;
DROP POLICY organism_lab_records_signed_scope_v1 ON public.organism_lab_records;
