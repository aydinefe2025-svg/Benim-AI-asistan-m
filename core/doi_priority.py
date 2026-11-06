"""Prioritize DOI identifiers explicitly named in the task."""
import re

_DOI = re.compile(r"10\.\d{4,9}/[A-Za-z0-9._;()/:+\-]{1,180}", re.I)


def requested_doi_leads(task, *, limit=3):
    """Return safe DOI source leads explicitly requested by the user."""
    if not isinstance(task, str) or type(limit) is not int or not 1 <= limit <= 5:
        return []
    leads, seen = [], set()
    for match in _DOI.finditer(task):
        doi = match.group(0).rstrip(".,;:!?)]}").lower()
        if ".." in doi or "//" in doi or doi in seen:
            continue
        seen.add(doi)
        leads.append({"title": "User-supplied DOI", "url": "https://doi.org/" + doi})
        if len(leads) >= limit:
            break
    return leads


def prioritize_requested_dois(task, candidates, *, limit=3):
    """Put all user-specified DOIs first, then fill with distinct search leads."""
    choices = candidates if isinstance(candidates, list) else []
    result, seen = [], set()
    for lead in requested_doi_leads(task, limit=limit) + choices:
        if not isinstance(lead, dict):
            continue
        url = lead.get("url")
        if not isinstance(url, str) or not url.casefold().startswith("https://doi.org/"):
            continue
        key = url.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(lead)
        if len(result) >= limit:
            break
    return result


def prioritize_requested_doi(task, candidates):
    return prioritize_requested_dois(task, candidates)
