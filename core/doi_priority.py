"""Prioritize DOIs typed in the task before other suggested source leads."""

import re


_DOI = re.compile(r"^10\.\d{4,9}/[A-Za-z0-9._;()/:+\-]{1,180}$", re.I)


def _requested_dois(task):
    if not isinstance(task, str):
        return []
    found = []
    for word in task.split():
        doi = word.split("doi.org/")[-1].strip("(),;:.?!").lower()
        if _DOI.fullmatch(doi) and ".." not in doi and doi not in found:
            found.append(doi)
    return found


def prioritize_requested_doi(task, candidates):
    """Put every explicitly cited DOI first while preserving other result order."""
    choices = candidates if isinstance(candidates, list) else []
    requested = _requested_dois(task)
    if not requested:
        return choices

    result = []
    for doi in requested:
        url = "https://doi.org/" + doi
        matched = next((item for item in choices if isinstance(item, dict)
                        and isinstance(item.get("url"), str)
                        and item["url"].casefold() == url.casefold()), None)
        title = matched.get("title") if matched else "User-supplied DOI"
        result.append({"title": title, "url": url})

    seen = {item["url"].casefold() for item in result}
    for item in choices:
        if (isinstance(item, dict) and isinstance(item.get("url"), str)
                and item["url"].casefold() not in seen):
            result.append(item)
            seen.add(item["url"].casefold())
    return result
