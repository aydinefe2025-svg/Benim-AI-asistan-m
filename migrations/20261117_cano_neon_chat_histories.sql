-- Additive migration for the *existing* Neon assistant_pg database.
-- Never run during Streamlit import or startup. Back up and review privileges first.
-- Existing private_memory_entries and task/colony data are unchanged.
BEGIN;

-- A one-time creation: NEVER silently repurpose an existing owner table.
-- Fail before any ALTER POLICY/GRANT. A prior or unexpected table must be
-- reviewed independently, not repaired implicitly by this migration.
DO $cano_chat_guard$
BEGIN
    IF to_regclass('public.cano_chat_histories') IS NOT NULL THEN
        RAISE EXCEPTION USING
            MESSAGE = 'CANO_CHAT_MIGRATION_PREEXISTING_TABLE';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'memory_runtime_app'
          AND NOT rolsuper AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION USING
            MESSAGE = 'CANO_CHAT_MIGRATION_UNSAFE_ROLE';
    END IF;
END
$cano_chat_guard$;

CREATE TABLE public.cano_chat_histories (
    owner_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT cano_chat_histories_payload_array
       CHECK (jsonb_typeof(payload) = 'array')
);

REVOKE ALL ON TABLE public.cano_chat_histories FROM PUBLIC;
ALTER TABLE public.cano_chat_histories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.cano_chat_histories FORCE ROW LEVEL SECURITY;

CREATE POLICY cano_chat_owner_read ON public.cano_chat_histories
    FOR SELECT TO memory_runtime_app
    USING (owner_key = current_setting('cano.owner_key', true));

CREATE POLICY cano_chat_owner_insert ON public.cano_chat_histories
    FOR INSERT TO memory_runtime_app
    WITH CHECK (owner_key = current_setting('cano.owner_key', true));

CREATE POLICY cano_chat_owner_update ON public.cano_chat_histories
    FOR UPDATE TO memory_runtime_app
    USING (owner_key = current_setting('cano.owner_key', true))
    WITH CHECK (owner_key = current_setting('cano.owner_key', true));

GRANT SELECT, INSERT, UPDATE ON public.cano_chat_histories TO memory_runtime_app;
COMMIT;
