-- Review candidate. Execute as dedicated table owner in a transaction.
-- Do not insert actual signing keys into source or logs. No RLS changes here.
CREATE SCHEMA cano_context_proof;
REVOKE ALL ON SCHEMA cano_context_proof FROM PUBLIC;
CREATE EXTENSION pgcrypto WITH SCHEMA cano_context_proof;
CREATE TABLE cano_context_proof.signing_key (role_name text PRIMARY KEY CHECK (role_name IN ('agent_task_app','cano_runtime_rw','cano_snapshot_app','cano_snapshot_runtime','memory_runtime_app','organism_lab_runtime')), secret bytea NOT NULL CHECK (octet_length(secret)=32));
REVOKE ALL ON TABLE cano_context_proof.signing_key FROM PUBLIC;
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
IF cano_context_proof.hmac(expected,signing_secret,'sha256') = cano_context_proof.hmac(decode(supplied,'hex'),signing_secret,'sha256') THEN RETURN scoped_owner; END IF;
RETURN NULL;
END $function$;
REVOKE ALL ON FUNCTION cano_context_proof.verified_owner() FROM PUBLIC;
GRANT USAGE ON SCHEMA cano_context_proof TO agent_task_app, cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, memory_runtime_app, organism_lab_runtime;
GRANT EXECUTE ON FUNCTION cano_context_proof.verified_owner() TO agent_task_app, cano_runtime_rw, cano_snapshot_app, cano_snapshot_runtime, memory_runtime_app, organism_lab_runtime;
