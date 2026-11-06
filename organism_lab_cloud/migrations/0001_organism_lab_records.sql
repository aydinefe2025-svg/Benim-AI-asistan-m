-- Additive schema for the authenticated Organism Lab archive.
-- Apply through the reviewed Neon migration workflow; the app never runs DDL.
CREATE TABLE IF NOT EXISTS public.organism_lab_records (
    owner_key TEXT NOT NULL CHECK (length(owner_key) BETWEEN 32 AND 128),
    collection TEXT NOT NULL CHECK (collection IN ('memory', 'chat_turn', 'literature', 'simulation', 'research_run', 'agent_activity')),
    record_id TEXT NOT NULL CHECK (length(record_id) BETWEEN 1 AND 200),
    payload JSONB NOT NULL CHECK (jsonb_typeof(payload) = 'object'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (owner_key, collection, record_id)
);
CREATE INDEX IF NOT EXISTS organism_lab_records_recent
    ON public.organism_lab_records (owner_key, collection, updated_at DESC);
