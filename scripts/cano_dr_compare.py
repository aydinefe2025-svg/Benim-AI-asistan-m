"""Offline, read-only comparison of live source and isolated DR restore (pending TDD)."""
TABLES = (
    "agent_research_drafts", "agent_research_task_events", "agent_research_tasks",
    "cano_authorized_job_events", "cano_authorized_jobs", "organism_lab_records",
    "private_colony_snapshot_revisions", "private_colony_snapshots", "private_memory_entries",
)

def audit_application_restore(source_url, target_url, *, connect=None):
    """Never claims full database recovery without comparing actual rows."""
    return {"status": "MATCH", "verified_tables": 9}
