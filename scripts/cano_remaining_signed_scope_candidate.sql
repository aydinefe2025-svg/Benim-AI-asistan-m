-- Candidate only. Apply atomically after actual app signing configuration is verified.
-- Preserve every existing permissive policy and grant, including the fixed-scope worker.
DO $$ BEGIN
 IF (SELECT count(*) FROM cano_context_proof.signing_key) <> 6 THEN RAISE EXCEPTION 'Signed owner key registry incomplete'; END IF;
 IF (SELECT count(*) FROM pg_class WHERE oid IN ('public.cano_code_jobs'::regclass,'public.organism_lab_records'::regclass) AND relrowsecurity) <> 2 THEN RAISE EXCEPTION 'Unexpected existing RLS state'; END IF;
 IF (SELECT count(*) FROM pg_policies WHERE schemaname='public' AND tablename IN ('cano_code_jobs','organism_lab_records')) <> 11 THEN RAISE EXCEPTION 'Unexpected policy inventory'; END IF;
 IF pg_has_role('cano_autodev_worker','agent_task_app','MEMBER') THEN RAISE EXCEPTION 'Worker role overlap'; END IF;
END $$;
CREATE POLICY cano_code_jobs_signed_scope_v1 ON public.cano_code_jobs AS RESTRICTIVE FOR ALL TO agent_task_app USING (owner_key=cano_context_proof.verified_owner()) WITH CHECK (owner_key=cano_context_proof.verified_owner());
CREATE POLICY organism_lab_records_signed_scope_v1 ON public.organism_lab_records AS RESTRICTIVE FOR ALL TO cano_snapshot_app,cano_runtime_rw,organism_lab_runtime USING (owner_key=cano_context_proof.verified_owner()) WITH CHECK (owner_key=cano_context_proof.verified_owner());
