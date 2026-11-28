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
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=registry AND contype='p' AND pg_get_constraintdef(oid)='PRIMARY KEY (role_name)')
       OR NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid=registry AND contype='c' AND position('octet_length(secret)' in pg_get_constraintdef(oid)) > 0)
       OR NOT EXISTS (SELECT 1 FROM pg_constraint
           WHERE conrelid=registry AND contype='c'
             AND position('agent_task_app' in pg_get_constraintdef(oid)) > 0
             AND position('cano_runtime_rw' in pg_get_constraintdef(oid)) > 0
             AND position('cano_snapshot_app' in pg_get_constraintdef(oid)) > 0
             AND position('cano_snapshot_runtime' in pg_get_constraintdef(oid)) > 0
             AND position('memory_runtime_app' in pg_get_constraintdef(oid)) > 0
             AND position('organism_lab_runtime' in pg_get_constraintdef(oid)) > 0)
       OR NOT EXISTS (SELECT 1 FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='pgcrypto' AND n.nspname='cano_context_proof') THEN
        RAISE EXCEPTION 'Existing signing registry or pgcrypto schema does not match the reviewed candidate';
    END IF;
    IF pg_get_userbyid((SELECT relowner FROM pg_class WHERE oid=registry)) <> current_user THEN
        RAISE EXCEPTION 'Signing registry must be owned by the executing table owner';
    END IF;
END
$validate_registry$;

CREATE OR REPLACE FUNCTION cano_context_proof.constant_time_equal(p_left bytea, p_right bytea)
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
REVOKE ALL ON FUNCTION cano_context_proof.constant_time_equal(bytea,bytea) FROM PUBLIC;

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
IF cano_context_proof.constant_time_equal(expected,decode(supplied,'hex')) THEN RETURN scoped_owner; END IF;
RETURN NULL;
END $function$;
REVOKE ALL ON FUNCTION cano_context_proof.verified_owner() FROM PUBLIC;
GRANT USAGE ON SCHEMA cano_context_proof TO agent_task_app, cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, memory_runtime_app, organism_lab_runtime;
GRANT EXECUTE ON FUNCTION cano_context_proof.verified_owner() TO agent_task_app, cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, memory_runtime_app, organism_lab_runtime;
