-- Review candidate. Execute as dedicated table owner in a transaction.
-- Do not insert actual signing keys into source or logs. No RLS changes here.
CREATE SCHEMA IF NOT EXISTS cano_context_proof;
REVOKE ALL ON SCHEMA cano_context_proof FROM PUBLIC;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA cano_context_proof;
CREATE TABLE IF NOT EXISTS cano_context_proof.signing_key (role_name text PRIMARY KEY CHECK (role_name IN ('agent_task_app','cano_runtime_rw','cano_snapshot_app','cano_snapshot_runtime','memory_runtime_app','organism_lab_runtime')), secret bytea NOT NULL CHECK (octet_length(secret)=32));
REVOKE ALL ON TABLE cano_context_proof.signing_key FROM PUBLIC;
DO $validate_registry$
DECLARE registry regclass := to_regclass('cano_context_proof.signing_key');
BEGIN
    IF registry IS NULL THEN
        RAISE EXCEPTION 'Signing registry is unavailable';
    END IF;
    IF (SELECT count(*) FROM pg_attribute
        WHERE attrelid=registry AND attnum > 0 AND NOT attisdropped) <> 2
       OR NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid=registry AND attname='role_name' AND atttypid='text'::regtype AND attnotnull AND NOT attisdropped)
       OR NOT EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid=registry AND attname='secret' AND atttypid='bytea'::regtype AND attnotnull AND NOT attisdropped)
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=registry AND contype='p' AND convalidated AND pg_get_constraintdef(oid)='PRIMARY KEY (role_name)')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=registry AND contype='c' AND convalidated AND pg_get_constraintdef(oid)='CHECK ((octet_length(secret) = 32))')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=registry AND contype='c' AND convalidated AND pg_get_constraintdef(oid)='CHECK ((role_name = ANY (ARRAY[''agent_task_app''::text, ''cano_runtime_rw''::text, ''cano_snapshot_app''::text, ''cano_snapshot_runtime''::text, ''memory_runtime_app''::text, ''organism_lab_runtime''::text])))')
       OR NOT EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgcrypto' AND n.nspname='cano_context_proof') THEN
        RAISE EXCEPTION 'Existing signing registry or pgcrypto schema does not match the reviewed candidate';
    END IF;
    IF pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=registry)) <> current_user THEN
        RAISE EXCEPTION 'Signing registry must be owned by the executing table owner';
    END IF;
END
$validate_registry$;

CREATE OR REPLACE FUNCTION cano_context_proof.fixed_work_equal(p_left bytea, p_right bytea)
RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path TO 'pg_catalog', 'pg_temp'
AS $function$
DECLARE difference integer := 0; idx integer; size integer;
BEGIN
    size := pg_catalog.octet_length(p_left);
    IF size <> pg_catalog.octet_length(p_right) THEN RETURN false; END IF;
    FOR idx IN 0..size-1 LOOP
        difference := difference | (pg_catalog.get_byte(p_left,idx) # pg_catalog.get_byte(p_right,idx));
    END LOOP;
    RETURN difference = 0;
END
$function$;
REVOKE ALL ON FUNCTION cano_context_proof.fixed_work_equal(bytea,bytea) FROM PUBLIC;

CREATE OR REPLACE FUNCTION cano_context_proof.verified_owner()
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'pg_temp'
AS $function$
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
END $function$;
REVOKE ALL ON FUNCTION cano_context_proof.verified_owner() FROM PUBLIC;
GRANT USAGE ON SCHEMA cano_context_proof TO agent_task_app, cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, memory_runtime_app, organism_lab_runtime;
GRANT EXECUTE ON FUNCTION cano_context_proof.verified_owner() TO agent_task_app, cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, memory_runtime_app, organism_lab_runtime;

DO $validate_security_acls$
DECLARE registry regclass := 'cano_context_proof.signing_key'::regclass;
        verifier oid := to_regprocedure('cano_context_proof.verified_owner()');
        comparator oid := to_regprocedure('cano_context_proof.fixed_work_equal(bytea,bytea)');
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_class c CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl,acldefault('r',c.relowner))) a
    WHERE c.oid=registry AND (a.grantee<>c.relowner OR a.is_grantable)
  ) THEN RAISE EXCEPTION 'Signing registry ACL is broader than its owner'; END IF;
  IF EXISTS (
    SELECT 1 FROM pg_namespace n CROSS JOIN LATERAL aclexplode(COALESCE(n.nspacl,acldefault('n',n.nspowner))) a
    WHERE n.oid='cano_context_proof'::regnamespace AND (
      a.is_grantable OR
      (a.grantee=n.nspowner AND a.privilege_type NOT IN ('CREATE','USAGE')) OR
      (a.grantee<>n.nspowner AND NOT EXISTS (
        SELECT 1 FROM (VALUES ('agent_task_app'),('cano_runtime_rw'),('cano_snapshot_app'),
          ('cano_snapshot_runtime'),('memory_runtime_app'),('organism_lab_runtime')) e(role_name)
        JOIN pg_roles r ON r.rolname=e.role_name WHERE r.oid=a.grantee AND a.privilege_type='USAGE'
      ))
    )
  ) THEN RAISE EXCEPTION 'Proof schema ACL has an unexpected principal or privilege'; END IF;
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
    WHERE NOT has_function_privilege(r.rolname, verifier, 'EXECUTE')
  ) THEN RAISE EXCEPTION 'Verifier ACL is not owner plus the six application roles'; END IF;
  IF comparator IS NULL OR NOT EXISTS (
    SELECT 1 FROM pg_proc p WHERE p.oid=comparator AND p.prolang=(SELECT oid FROM pg_language WHERE lanname='plpgsql')
      AND p.provolatile='i' AND p.proisstrict AND NOT p.prosecdef
      AND p.proconfig @> ARRAY['search_path=pg_catalog, pg_temp']
      AND position('FOR idx IN 0..size-1 LOOP' in p.prosrc)>0
      AND position('difference := difference |' in p.prosrc)>0
  ) OR EXISTS (
    SELECT 1 FROM pg_proc p CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a
    WHERE p.oid=comparator AND (a.grantee<>p.proowner OR a.privilege_type<>'EXECUTE' OR a.is_grantable)
  ) THEN RAISE EXCEPTION 'Fixed-work comparator definition or ACL drifted'; END IF;
END
$validate_security_acls$;
