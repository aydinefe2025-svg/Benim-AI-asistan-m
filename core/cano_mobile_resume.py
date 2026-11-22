"""Choose an owner-loaded blocked mission for a phone-friendly resume link.

Selection is not authentication: the caller must have restored an authenticated
owner's local colony before applying this purely visual filter.
"""
import re

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
