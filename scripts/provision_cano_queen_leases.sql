-- Admin-only provisioning for future owner-scoped PostgreSQL queen leases.
-- NEVER run this migration automatically on Render. Review privileges and backup
-- before deployment. Runtime does not create schema or enroll nodes.
CREATE TABLE IF NOT EXISTS public.cano_queen_authorized_nodes (
    owner_key TEXT NOT NULL,
    node_id TEXT NOT NULL,
    verifier BYTEA NOT NULL CHECK (octet_length(verifier) = 32),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (owner_key, node_id)
);
CREATE TABLE IF NOT EXISTS public.cano_queen_leases (
    owner_key TEXT NOT NULL,
    scope TEXT NOT NULL,
    node_id TEXT NOT NULL,
    epoch BIGINT NOT NULL CHECK (epoch >= 1),
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (owner_key, scope),
    FOREIGN KEY (owner_key,node_id) REFERENCES public.cano_queen_authorized_nodes(owner_key,node_id)
);
-- Do not grant access to public users. A distinct authenticated CANO
-- runtime DB role will require SELECT on node verifiers and SELECT/INSERT/
-- UPDATE on leases. Authorize only intentionally managed, owner-owned nodes.
REVOKE ALL ON public.cano_queen_authorized_nodes FROM PUBLIC;
REVOKE ALL ON public.cano_queen_leases FROM PUBLIC;
