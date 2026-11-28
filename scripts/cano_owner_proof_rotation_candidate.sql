-- Reviewed candidate only. Run as registry owner in one transaction.
-- No key material is provisioned; no RLS or grants are changed.
ALTER TABLE cano_context_proof.signing_key ADD COLUMN previous_secret bytea, ADD COLUMN previous_valid_until timestamptz, ADD CONSTRAINT signing_key_rotation_pair CHECK ((previous_secret IS NULL AND previous_valid_until IS NULL) OR (previous_secret IS NOT NULL AND previous_valid_until IS NOT NULL AND octet_length(previous_secret)=32 AND previous_secret<>secret));
CREATE OR REPLACE FUNCTION cano_context_proof.verified_owner()
 RETURNS text
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog', 'pg_temp'
AS $function$
DECLARE caller text; scoped_owner text; supplied text; signing_secret bytea; expected bytea; previous_secret bytea; previous_valid_until timestamptz; 
BEGIN
caller := CASE WHEN current_setting('role',true) IS NULL OR current_setting('role',true)='none' THEN session_user::text ELSE current_setting('role',true) END;
scoped_owner := current_setting('cano.owner_key',true);
supplied := current_setting('cano.owner_proof',true);
IF scoped_owner IS NULL OR scoped_owner !~ '^[a-zA-Z0-9_-]{1,128}$' OR supplied IS NULL OR supplied !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
SELECT k.secret, k.previous_secret, k.previous_valid_until INTO signing_secret, previous_secret, previous_valid_until FROM cano_context_proof.signing_key k WHERE k.role_name=caller;
IF signing_secret IS NULL THEN RETURN NULL; END IF;
expected := cano_context_proof.hmac(convert_to(caller||':'||scoped_owner||':'||pg_current_xact_id()::text||':'||pg_backend_pid()::text,'UTF8'),signing_secret,'sha256');
IF cano_context_proof.hmac(expected,signing_secret,'sha256') = cano_context_proof.hmac(decode(supplied,'hex'),signing_secret,'sha256') THEN RETURN scoped_owner; END IF;
IF previous_secret IS NOT NULL AND previous_valid_until > statement_timestamp() THEN
expected := cano_context_proof.hmac(convert_to(caller||':'||scoped_owner||':'||pg_current_xact_id()::text||':'||pg_backend_pid()::text,'UTF8'),previous_secret,'sha256');
IF cano_context_proof.hmac(expected,previous_secret,'sha256') = cano_context_proof.hmac(decode(supplied,'hex'),previous_secret,'sha256') THEN RETURN scoped_owner; END IF;
END IF;
RETURN NULL;
END $function$;
