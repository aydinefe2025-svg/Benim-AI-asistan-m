"""Authenticated-owner boundary for explicitly delegated network tasks."""
from core.postgres_local_grant import PostgresLocalGrant

def _owner(queue, owner_key, approved):
    if approved is not True or not owner_key or queue.owner_key != owner_key:
        raise PermissionError("Explicit authenticated owner authorization required")

def issue_for_owner(queue, *, owner_key, environment, approved=False):
    _owner(queue, owner_key, approved)
    if environment.get("CANO_LOCAL_GRANT_ENABLED") != "1":
        raise PermissionError("Network delegation disabled")
    return PostgresLocalGrant.issue(queue, approved=True)

def revoke_for_owner(queue, job_id, *, owner_key, approved=False):
    _owner(queue, owner_key, approved)
    # Revocation remains available even if issuance was disabled.
    return PostgresLocalGrant.revoke(queue, job_id, approved=True)
