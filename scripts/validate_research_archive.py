"""Validate archived research source leads without treating links as verified facts."""
import json
import sys
import re
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED_TOPICS = {"neutron_star_eos", "history_inventions", "robotics", "open_source_ai"}
DOI = re.compile(r"10\.\d{4,9}/[^\s<>\"#?]+", re.IGNORECASE)


def _valid_wikipedia_url(url):
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.hostname == "en.wikipedia.org" and
                not parts.username and not parts.password and not parts.port and
                not parts.query and not parts.fragment and parts.path.startswith("/wiki/"))
    except ValueError:
        return False


def _valid_doi_url(url, doi):
    if not isinstance(url, str):
        return False
    try:
        parts = urlsplit(url)
        return (parts.scheme == "https" and parts.netloc.lower() == "doi.org" and
                parts.path == "/" + doi and not parts.query and not parts.fragment)
    except ValueError:
        return False


def validate(path, *, require_scholarly=False):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = []
    if not isinstance(data, dict):
        return ["report must be a JSON object"]
    if not data.get("generated_at"):
        problems.append("missing timestamp")
    if data.get("verified") is not False:
        problems.append("source leads must not claim independent verification")
    topics = data.get("topics", {})
    if set(topics) != EXPECTED_TOPICS:
        problems.append("missing or unexpected research topics")
    for name in EXPECTED_TOPICS:
        entry = topics.get(name, {}) if isinstance(topics, dict) else {}
        if not isinstance(entry, dict):
            problems.append(name + ": invalid topic entry")
            continue
        if entry.get("status") != "found":
            problems.append(name + ": no sources found")
        links = entry.get("sources", [])
        if not isinstance(links, list) or not links:
            problems.append(name + ": empty source list")
            links = []
        seen = set()
        for item in links:
            if not isinstance(item, dict):
                problems.append(name + ": invalid source entry")
                continue
            url = item.get("url", "")
            if not _valid_wikipedia_url(url):
                problems.append(name + ": invalid source URL")
            if url in seen:
                problems.append(name + ": duplicate source")
            seen.add(url)

    scholarly = data.get("scholarly_topics")
    if scholarly is None and not require_scholarly:
        return problems
    if not isinstance(scholarly, dict):
        problems.append("missing or invalid scholarly topics")
        return problems
    if set(scholarly) != EXPECTED_TOPICS:
        problems.append("missing or unexpected scholarly topics")
    for name in EXPECTED_TOPICS:
        entry = scholarly.get(name, {})
        if not isinstance(entry, dict):
            problems.append(name + ": invalid scholarly topic entry")
            continue
        if entry.get("verified") is not False:
            problems.append(name + ": scholarly metadata must remain unverified")
        sources = entry.get("sources", [])
        status = entry.get("status")
        if not isinstance(sources, list) or len(sources) > 3:
            problems.append(name + ": invalid scholarly source list")
            continue
        if status not in ({"metadata_only", "error"} if not sources else {"metadata_only"}):
            problems.append(name + ": invalid scholarly status")
        seen_dois = set()
        for item in sources:
            if not isinstance(item, dict):
                problems.append(name + ": invalid scholarly source entry")
                continue
            doi, url = item.get("doi"), item.get("url", "")
            if not isinstance(doi, str) or DOI.fullmatch(doi) is None:
                problems.append(name + ": invalid DOI")
                continue
            normalized_doi = doi.lower()
            if not _valid_doi_url(url, doi):
                problems.append(name + ": DOI URL does not match DOI")
            if normalized_doi in seen_dois:
                problems.append(name + ": duplicate DOI")
            seen_dois.add(normalized_doi)
            if not isinstance(item.get("title"), str) or not item["title"].strip():
                problems.append(name + ": missing scholarly title")
            if (item.get("verified") is not False or item.get("stage") != "source_lead" or
                    item.get("retrieval") != "publisher_metadata" or
                    item.get("primary_source_review") != "required" or
                    item.get("confidence") != "unassessed"):
                problems.append(name + ": scholarly source must remain an unverified lead")
    return problems

if __name__ == "__main__":
    require_scholarly = "--require-scholarly" in sys.argv
    args = [arg for arg in sys.argv[1:] if arg != "--require-scholarly"]
    files = [Path(p) for p in args] or sorted(Path("research_reports").glob("*.json"))
    if not files:
        print("No research reports found", file=sys.stderr)
        sys.exit(1)
    errors = [f"{p}: {issue}" for p in files for issue in validate(p, require_scholarly=require_scholarly)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    print(f"Validated {len(files)} research report(s)")

