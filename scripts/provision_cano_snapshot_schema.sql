-- Additive schema for owner-scoped CANO snapshot history.
-- Run as the database owner during deployment; the web runtime never runs DDL.
CREATE TABLE IF NOT EXISTS public.private_colony_snapshot_revisions (
    revision BIGSERIAL PRIMARY KEY,
    owner_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_colony_revision_owner
    ON public.private_colony_snapshot_revisions (owner_key, revision DESC);
