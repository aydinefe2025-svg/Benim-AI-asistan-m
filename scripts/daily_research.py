"""Generate a bounded, auditable research snapshot without an LLM key."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from core.public_research import research_sources

TOPICS = {
    "neutron_star_eos": "neutron star equation of state NICER",
    "history_inventions": "history of engineering inventions",
    "robotics": "robotics biomimetics",
    "open_source_ai": "open source artificial intelligence agents",
}

def run(fetch=None, output_dir="research_reports"):
    now = datetime.now(timezone.utc)
    report = {"generated_at": now.isoformat(), "status": "source_leads_only",
              "verified": False, "topics": {}}
    for key, query in TOPICS.items():
        for attempt in range(1, 4):
            try:
                links = research_sources(query, limit=3, fetch=fetch)
                if not links:
                    raise ValueError("No source leads returned")
                report["topics"][key] = {"query": query, "sources": links,
                                         "status": "found", "attempts": attempt}
                break
            except Exception as exc:
                report["topics"][key] = {"query": query, "sources": [],
                                         "status": "error", "error_type": type(exc).__name__,
                                         "attempts": attempt}
    path = Path(output_dir) / (now.strftime("%Y-%m-%d") + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path

if __name__ == "__main__":
    print(run())
