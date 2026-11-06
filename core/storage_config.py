"""Resolve separate environment URLs for the CANO and memory stores."""
from urllib.parse import urlsplit


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


def database_provider_label(database_url):
    """Return a safe provider label without exposing connection details."""
    if not isinstance(database_url, str) or not database_url.strip():
        return "yapılandırılmamış"
    try:
        host = (urlsplit(database_url.strip()).hostname or "").casefold().rstrip(".")
    except ValueError:
        return "tanınmayan PostgreSQL"
    if not host:
        return "tanınmayan PostgreSQL"
    if host.endswith(".neon.tech") or host.endswith(".neon.build"):
        return "Neon"
    if host.endswith(".render.com"):
        return "Render"
    if host in {"localhost", "127.0.0.1", "::1"}:
        return "yerel PostgreSQL"
    return "harici PostgreSQL"

