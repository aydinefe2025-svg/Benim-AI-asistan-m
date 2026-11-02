"""Validate archived research source leads without treating links as verified facts."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

EXPECTED_TOPICS = {"neutron_star_eos", "history_inventions", "robotics", "open_source_ai"}

def validate(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    problems = []
    if not data.get("generated_at"):
        problems.append("missing timestamp")
    if data.get("verified") is not False:
        problems.append("source leads must not claim independent verification")
    topics = data.get("topics", {})
    if set(topics) != EXPECTED_TOPICS:
        problems.append("missing or unexpected research topics")
    for name in EXPECTED_TOPICS:
        entry = topics.get(name, {})
        if entry.get("status") != "found":
            problems.append(name + ": no sources found")
        links = entry.get("sources", [])
        if not links:
            problems.append(name + ": empty source list")
        seen = set()
        for item in links:
            url = item.get("url", "")
            parts = urlsplit(url)
            if parts.scheme != "https" or parts.hostname != "en.wikipedia.org" or not parts.path.startswith("/wiki/"):
                problems.append(name + ": invalid source URL")
            if url in seen:
                problems.append(name + ": duplicate source")
            seen.add(url)
    return problems

if __name__ == "__main__":
    files = [Path(p) for p in sys.argv[1:]] or sorted(Path("research_reports").glob("*.json"))
    if not files:
        print("No research reports found", file=sys.stderr)
        sys.exit(1)
    errors = [f"{p}: {issue}" for p in files for issue in validate(p)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        sys.exit(1)
    print(f"Validated {len(files)} research report(s)")
