"""Resolve separate environment URLs for the CANO and memory stores."""


def cano_database_url(environ):
    """Prefer the least-privilege CANO-only URL, with legacy fallback."""
    return environ.get("CANO_DATABASE_URL") or environ.get("DATABASE_URL")


def memory_database_url(environ):
    """Do not use a CANO-only credential for the general memory store."""
    explicit = environ.get("MEMORY_DATABASE_URL")
    if explicit:
        return explicit
    if environ.get("CANO_DATABASE_URL"):
        return None
    return environ.get("DATABASE_URL")
