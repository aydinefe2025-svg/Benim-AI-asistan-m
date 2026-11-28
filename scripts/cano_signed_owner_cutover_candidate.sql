-- Review candidate; run in one transaction only after approved protected key provisioning and app deployment.
DO $$
DECLARE verifier oid := to_regprocedure('cano_context_proof.verified_owner()');
BEGIN
 IF (SELECT count(*) FROM cano_context_proof.signing_key) <> 6
    OR (SELECT count(DISTINCT secret) FROM cano_context_proof.signing_key) <> 6
    OR (SELECT count(DISTINCT role_name) FROM cano_context_proof.signing_key) <> 6 THEN
   RAISE EXCEPTION 'Signed owner key registry incomplete or duplicated';
 END IF;
 IF EXISTS (
   SELECT 1 FROM (VALUES
     ('agent_task_app',true),('cano_runtime_rw',true),('cano_snapshot_app',true),
     ('cano_snapshot_runtime',false),('memory_runtime_app',true),('organism_lab_runtime',true)
   ) AS expected(role_name,can_login)
   LEFT JOIN pg_roles r ON r.rolname=expected.role_name
   WHERE r.oid IS NULL OR r.rolcanlogin<>expected.can_login OR r.rolsuper OR r.rolbypassrls
 ) THEN RAISE EXCEPTION 'Live application role login/bypass matrix differs from reviewed design'; END IF;
 IF (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relkind='r' AND c.relname IN
     ('agent_research_drafts','agent_research_task_events','agent_research_tasks','cano_authorized_job_events','cano_authorized_jobs','private_colony_snapshot_revisions','private_colony_snapshots','private_memory_entries')) <> 8 THEN
   RAISE EXCEPTION 'Owner RLS target table set is incomplete';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
     WHERE n.nspname='public' AND c.relname IN
     ('agent_research_drafts','agent_research_task_events','agent_research_tasks','cano_authorized_job_events','cano_authorized_jobs','private_colony_snapshot_revisions','private_colony_snapshots','private_memory_entries')
       AND (c.relrowsecurity OR c.relforcerowsecurity OR pg_get_userbyid(c.relowner)<>current_user::text)) THEN
   RAISE EXCEPTION 'Unexpected pre-cutover RLS or table-owner state';
 END IF;
 IF EXISTS (SELECT 1 FROM pg_policies WHERE schemaname='public' AND tablename IN
     ('agent_research_drafts','agent_research_task_events','agent_research_tasks','cano_authorized_job_events','cano_authorized_jobs','private_colony_snapshot_revisions','private_colony_snapshots','private_memory_entries')) THEN
   RAISE EXCEPTION 'Unexpected pre-existing policy on owner RLS targets';
 END IF;
 IF verifier IS NULL OR NOT EXISTS (
   SELECT 1 FROM pg_proc p WHERE p.oid=verifier AND p.prosecdef
     AND p.proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
     AND p.proconfig @> ARRAY['search_path=pg_catalog, pg_temp']
 ) OR EXISTS (
   SELECT 1 FROM pg_proc p
   CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) acl
   WHERE p.oid=verifier AND acl.grantee=0 AND acl.privilege_type='EXECUTE'
 ) THEN
   RAISE EXCEPTION 'Owner verifier security attributes are not as reviewed';
 END IF;
 IF EXISTS (
   SELECT 1 FROM (VALUES ('agent_task_app'),('cano_runtime_rw'),('cano_snapshot_app'),
     ('cano_snapshot_runtime'),('memory_runtime_app'),('organism_lab_runtime')) AS roles(role_name)
   WHERE has_table_privilege(role_name,'cano_context_proof.signing_key','SELECT')
      OR has_table_privilege(role_name,'cano_context_proof.signing_key','INSERT')
      OR has_table_privilege(role_name,'cano_context_proof.signing_key','UPDATE')
      OR has_table_privilege(role_name,'cano_context_proof.signing_key','DELETE')
 ) THEN RAISE EXCEPTION 'Signing registry grants access to an application role'; END IF;
END $$;
DO $validate_cutover_drift$
DECLARE verifier oid := to_regprocedure('cano_context_proof.verified_owner()');
        comparator oid := to_regprocedure('cano_context_proof.fixed_work_equal(bytea,bytea)');
        registry oid := 'cano_context_proof.signing_key'::regclass;
        registry_owner oid := (SELECT relowner FROM pg_class WHERE oid='cano_context_proof.signing_key'::regclass);
BEGIN
  IF EXISTS (
    SELECT 1 FROM (VALUES ('agent_task_app'),('cano_runtime_rw'),('cano_snapshot_app'),
      ('cano_snapshot_runtime'),('memory_runtime_app'),('organism_lab_runtime')) e(role_name)
    LEFT JOIN cano_context_proof.signing_key k USING(role_name)
    WHERE k.role_name IS NULL
  ) OR EXISTS (
    SELECT role_name FROM cano_context_proof.signing_key
    EXCEPT SELECT role_name FROM (VALUES ('agent_task_app'),('cano_runtime_rw'),('cano_snapshot_app'),
      ('cano_snapshot_runtime'),('memory_runtime_app'),('organism_lab_runtime')) e(role_name)
  ) THEN RAISE EXCEPTION 'Signing registry does not contain exactly the six expected roles'; END IF;

  IF EXISTS (
    SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
    WHERE c.oid=registry AND (a.grantee<>registry_owner OR a.is_grantable)
  ) THEN RAISE EXCEPTION 'Signing registry ACL includes a non-owner or grant option'; END IF;

  IF EXISTS (
    SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
    WHERE p.oid=verifier AND (a.is_grantable OR a.privilege_type<>'EXECUTE' OR
      (a.grantee<>p.proowner AND NOT EXISTS (
        SELECT 1 FROM (VALUES ('agent_task_app'),('cano_runtime_rw'),('cano_snapshot_app'),
          ('cano_snapshot_runtime'),('memory_runtime_app'),('organism_lab_runtime')) e(role_name)
        JOIN pg_roles r ON r.rolname=e.role_name WHERE r.oid=a.grantee
      )))
  ) OR EXISTS (
    SELECT 1 FROM (VALUES ('agent_task_app'),('cano_runtime_rw'),('cano_snapshot_app'),
      ('cano_snapshot_runtime'),('memory_runtime_app'),('organism_lab_runtime')) e(role_name)
    JOIN pg_roles r ON r.rolname=e.role_name
    WHERE NOT has_function_privilege(r.rolname,verifier,'EXECUTE')
  ) THEN RAISE EXCEPTION 'Verifier ACL is not restricted to the owner and expected roles'; END IF;

  IF verifier IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_proc p WHERE p.oid=verifier AND p.prosrc=$expected_verified_owner$
DECLARE caller text; scoped_owner text; supplied text; signing_secret bytea; expected bytea; 
BEGIN
caller := CASE WHEN current_setting('role',true) IS NULL OR current_setting('role',true)='none' THEN session_user::text ELSE current_setting('role',true) END;
scoped_owner := current_setting('cano.owner_key',true);
supplied := current_setting('cano.owner_proof',true);
IF scoped_owner IS NULL OR scoped_owner !~ '^[a-zA-Z0-9_-]{1,128}$' OR supplied IS NULL OR supplied !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
SELECT secret INTO signing_secret FROM cano_context_proof.signing_key WHERE role_name=caller;
IF signing_secret IS NULL THEN RETURN NULL; END IF;
expected := cano_context_proof.hmac(convert_to(caller||':'||scoped_owner||':'||pg_current_xact_id()::text||':'||pg_backend_pid()::text,'UTF8'),signing_secret,'sha256');
IF cano_context_proof.fixed_work_equal(expected,decode(supplied,'hex')) THEN RETURN scoped_owner; END IF;
RETURN NULL;
END $expected_verified_owner$
      AND p.prosecdef AND p.proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
      AND p.proconfig @> ARRAY['search_path=pg_catalog, pg_temp']
  ) THEN RAISE EXCEPTION 'Verifier source or security attributes differ from reviewed candidate'; END IF;

  IF comparator IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_proc p WHERE p.oid=comparator AND p.prosrc=$expected_fixed_work_equal$
DECLARE difference integer := 0; idx integer; size integer;
BEGIN
    size := pg_catalog.octet_length(p_left);
    IF size <> pg_catalog.octet_length(p_right) THEN RETURN false; END IF;
    FOR idx IN 0..size-1 LOOP
        difference := difference | (pg_catalog.get_byte(p_left,idx) # pg_catalog.get_byte(p_right,idx));
    END LOOP;
    RETURN difference = 0;
END
$expected_fixed_work_equal$
      AND p.prolang=(SELECT oid FROM pg_language WHERE lanname='plpgsql')
      AND p.provolatile='i' AND p.proisstrict AND NOT p.prosecdef
      AND p.proowner=(SELECT oid FROM pg_roles WHERE rolname=current_user)
      AND p.proconfig @> ARRAY['search_path=pg_catalog, pg_temp']
  ) OR EXISTS (
    SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
    WHERE p.oid=comparator AND (a.grantee<>p.proowner OR a.privilege_type<>'EXECUTE' OR a.is_grantable)
  ) THEN RAISE EXCEPTION 'Comparator source, security attributes, or ACL differ from reviewed candidate'; END IF;

  IF NOT EXISTS (
    WITH RECURSIVE paths(role_oid, can_set, visited) AS (
      SELECT m.roleid, m.set_option, ARRAY[m.member,m.roleid]
      FROM pg_auth_members m
      WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname='cano_snapshot_app')
      UNION ALL
      SELECT m.roleid, p.can_set AND m.set_option, p.visited || m.roleid
      FROM paths p JOIN pg_auth_members m ON m.member=p.role_oid
      WHERE NOT m.roleid=ANY(p.visited)
    )
    SELECT 1 FROM paths
    WHERE role_oid=(SELECT oid FROM pg_roles WHERE rolname='cano_snapshot_runtime') AND can_set
  ) THEN RAISE EXCEPTION 'No reviewed SET ROLE path from cano_snapshot_app to NOLOGIN cano_snapshot_runtime'; END IF;
END
$validate_cutover_drift$;

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
