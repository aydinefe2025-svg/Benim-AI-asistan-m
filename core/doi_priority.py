"""Prioritize a DOI typed in the task before other suggested source leads."""

def prioritize_requested_doi(task, candidates):
    choices = candidates if isinstance(candidates, list) else []
    if not isinstance(task, str):
        return choices
    for word in task.split():
        doi = word.strip("(),;").lower()
        if doi.startswith("10.") and "/" in doi and len(doi) < 195:
            url = "https://doi.org/" + doi
            matched = next((a for a in choices if isinstance(a, dict) and
                            a.get("url", "").casefold() == url), None)
            title = matched.get("title") if matched else "User-supplied DOI"
            return [{"title": title, "url": url}, *choices]
    return choices
