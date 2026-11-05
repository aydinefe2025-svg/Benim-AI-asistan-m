"""Fail-closed owner snapshot CAS for the secondary CANO evidence page.

The main CANO cockpit establishes owner-bound snapshot provenance. Never infer
ownership from a page URL or untrusted local SQLite records. Never advance a
session's expected version before PostgreSQL confirms its atomic write.
"""


def save_owner_checkpoint(store, owner_key, session_state, snapshot, *,
                          archive_prior=True):
    """CAS-save a checkpoint using the exact owner snapshot previously read."""
    if (not isinstance(owner_key, str) or not owner_key.strip()
            or session_state.get("_cano_backup_owner_key") != owner_key
            or "_cano_backup_expected" not in session_state):
        raise RuntimeError("Authenticated owner backup baseline is missing")
    expected = session_state["_cano_backup_expected"]
    store.save_versioned_verified(
        owner_key, snapshot, expected_prior=expected,
        archive_prior=archive_prior)
    session_state["_cano_backup_expected"] = snapshot


def bind_restored_owner_baseline(store, owner_key, session_state):
    """Read back and bind an explicitly restored owner's latest snapshot.

    Called only after successful consent-based restore. A prior session owner
    cannot be silently switched. Never synthesize a baseline if the backup
    readback is unavailable or malformed.
    """
    if not isinstance(owner_key, str) or not owner_key.strip():
        raise PermissionError("Authenticated owner is required")
    if session_state.get("_cano_backup_owner_key") not in (None, owner_key):
        raise PermissionError("Previous authenticated owner differs")
    latest = store.load(owner_key)
    if (not isinstance(latest, dict)
            or not all(isinstance(latest.get(k), list)
                       for k in ("agents", "feedback", "reviews"))):
        raise RuntimeError("Restored owner snapshot readback invalid")
    session_state["_cano_backup_owner_key"] = owner_key
    session_state["_cano_backup_expected"] = latest
    return latest
