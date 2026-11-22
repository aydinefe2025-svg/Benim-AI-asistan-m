"""Choose an owner-loaded blocked mission for a phone-friendly resume link.

Selection is not authentication: the caller must have restored an authenticated
owner's local colony before applying this purely visual filter.
"""
import re
import sqlite3

_MISSION_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
)


def select_mobile_resume_items(items, requested=None):
    """Show blocked tasks; a valid explicit UUID shows exactly one matching task."""
    blocked = [
        item for item in items
        if isinstance(item, dict) and item.get("status") == "blocked"
    ]
    if requested is None or requested == "":
        return blocked
    if not isinstance(requested, str) or not _MISSION_ID.fullmatch(requested):
        return []
    return [item for item in blocked if item.get("id") == requested]

def select_mobile_completed_mission(get_mission, requested=None):
    """Return one owner-loaded completed ID for read-only review, not resume.

    The caller must first restore the OIDC-authenticated owner's colony.
    Invalid/missing IDs are never sent to the database.
    """
    if not isinstance(requested, str) or not _MISSION_ID.fullmatch(requested):
        return None
    try:
        saved = get_mission(requested)
    except (KeyError, ValueError, sqlite3.Error):
        return None
    if not isinstance(saved, dict) or saved.get("id") != requested:
        return None
    stages = saved.get("stages")
    if (saved.get("status") != "review_pending"
            or not isinstance(stages, list) or len(stages) != 4
            or [stage.get("role") for stage in stages if isinstance(stage, dict)]
            != ["planner", "researcher", "reviewer", "synthesis"]):
        return None
    return requested
