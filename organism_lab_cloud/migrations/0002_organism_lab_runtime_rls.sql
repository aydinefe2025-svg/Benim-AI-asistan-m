-- Permit the hosted lab runtime to access only its authenticated owner's
-- single filesystem snapshot. The application sets organism.owner_key
-- transaction-locally on every connection before issuing archive queries.
REVOKE ALL ON public.organism_lab_records FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO organism_lab_runtime;
GRANT SELECT, INSERT, UPDATE ON public.organism_lab_records TO organism_lab_runtime;
ALTER TABLE public.organism_lab_records ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'organism_lab_records'
          AND policyname = 'organism_lab_runtime_snapshot_select'
    ) THEN
        CREATE POLICY organism_lab_runtime_snapshot_select
            ON public.organism_lab_records FOR SELECT TO organism_lab_runtime
            USING (
                owner_key = current_setting('organism.owner_key', true)
                AND collection = 'simulation'
                AND record_id = 'filesystem_snapshot_v1'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'organism_lab_records'
          AND policyname = 'organism_lab_runtime_snapshot_insert'
    ) THEN
        CREATE POLICY organism_lab_runtime_snapshot_insert
            ON public.organism_lab_records FOR INSERT TO organism_lab_runtime
            WITH CHECK (
                owner_key = current_setting('organism.owner_key', true)
                AND collection = 'simulation'
                AND record_id = 'filesystem_snapshot_v1'
            );
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'organism_lab_records'
          AND policyname = 'organism_lab_runtime_snapshot_update'
    ) THEN
        CREATE POLICY organism_lab_runtime_snapshot_update
            ON public.organism_lab_records FOR UPDATE TO organism_lab_runtime
            USING (
                owner_key = current_setting('organism.owner_key', true)
                AND collection = 'simulation'
                AND record_id = 'filesystem_snapshot_v1'
            )
            WITH CHECK (
                owner_key = current_setting('organism.owner_key', true)
                AND collection = 'simulation'
                AND record_id = 'filesystem_snapshot_v1'
            );
    END IF;
END
$$;
