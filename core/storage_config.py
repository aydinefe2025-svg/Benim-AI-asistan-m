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



def database_binding_providers(environ):
    """Safe runtime provider classes for the three effective CANO stores.

    Resolves legacy fallbacks exactly like the application, never returning
    credentials, hostnames, database names, or connection parameters.
    """
    return {
        "cano": database_provider_label(cano_database_url(environ)),
        "memory": database_provider_label(memory_database_url(environ)),
        "task": database_provider_label(environ.get("AGENT_TASK_DATABASE_URL")),
    }


# A startup RLS diagnosis may expose only known internal role names, never
# arbitrary URI usernames, passwords, hosts, paths or query parameters.
_ALLOWED_CANO_ROLE_CLASSES = frozenset({
    "cano_runtime_rw", "cano_snapshot_app", "organism_lab_runtime",
    "cano_snapshot_runtime", "assistant_owner",
})


def cano_login_role_class(environ):
    """Return an allowlisted class of the effective CANO DB login, not a URI."""
    url = cano_database_url(environ)
    if not isinstance(url, str) or not url.strip():
        return "unconfigured"
    try:
        username = urlsplit(url.strip()).username
    except ValueError:
        return "other"
    return username if username in _ALLOWED_CANO_ROLE_CLASSES else "other"
