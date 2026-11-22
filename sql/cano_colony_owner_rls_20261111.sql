-- CANO tenant-scoped colony RLS: REVIEW-ONLY MIGRATION, NEVER run on live DB
-- without verified independent backup, selected restricted runtime role and
-- human-approved maintenance/rollback plan.
-- This SQL deliberately fails if a policy already exists on either target.
BEGIN;

DO $$
DECLARE bad_role boolean;
BEGIN
  SELECT NOT EXISTS (
    SELECT 1 FROM pg_roles
    WHERE rolname='cano_snapshot_app' AND NOT rolsuper AND NOT rolbypassrls
  ) INTO bad_role;
  IF bad_role THEN
    RAISE EXCEPTION 'Expected non-superuser, non-BYPASSRLS cano_snapshot_app role';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='public'
      AND c.relname IN ('private_colony_snapshots','private_colony_snapshot_revisions')
      AND pg_has_role('cano_snapshot_app',c.relowner,'USAGE')
  ) THEN
    RAISE EXCEPTION 'Runtime role must not inherit table owner';
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname='public'
      AND tablename IN ('private_colony_snapshots','private_colony_snapshot_revisions')
  ) THEN
    RAISE EXCEPTION 'Existing policies require manual review; do not overwrite';
  END IF;
END $$;

ALTER TABLE public.private_colony_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.private_colony_snapshot_revisions ENABLE ROW LEVEL SECURITY;

CREATE POLICY cano_colony_snapshot_select ON public.private_colony_snapshots
  FOR SELECT TO cano_snapshot_app
  USING (owner_key = NULLIF(current_setting('cano.owner_key', true), ''));
CREATE POLICY cano_colony_snapshot_insert ON public.private_colony_snapshots
  FOR INSERT TO cano_snapshot_app
  WITH CHECK (owner_key = NULLIF(current_setting('cano.owner_key', true), ''));
CREATE POLICY cano_colony_snapshot_update ON public.private_colony_snapshots
  FOR UPDATE TO cano_snapshot_app
  USING (owner_key = NULLIF(current_setting('cano.owner_key', true), ''))
  WITH CHECK (owner_key = NULLIF(current_setting('cano.owner_key', true), ''));

CREATE POLICY cano_colony_revision_select ON public.private_colony_snapshot_revisions
  FOR SELECT TO cano_snapshot_app
  USING (owner_key = NULLIF(current_setting('cano.owner_key', true), ''));
CREATE POLICY cano_colony_revision_insert ON public.private_colony_snapshot_revisions
  FOR INSERT TO cano_snapshot_app
  WITH CHECK (owner_key = NULLIF(current_setting('cano.owner_key', true), ''));

-- Do not grant new privileges, drop data, disable other roles, FORCE owner RLS,
-- or set the deployment's DATABASE_URL as part of this migration.
COMMIT;
