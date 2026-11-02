"""Import externally sourced research records into the existing evidence store.

Input is a JSON array. Every record needs source_url, title, and claim.
Claims are deliberately unreviewed; importing a source is not verification.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.knowledge_store import KnowledgeStore


def ingest_records(records: list[dict], db_path: str | Path) -> dict[str, int]:
    if not isinstance(records, list):
        raise ValueError("Input must be a JSON array")
    # Validate the entire batch before touching the database.
    normalized = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Record {index} must be an object")
        for key in ("source_url", "title", "claim"):
            if not isinstance(record.get(key), str) or not record[key].strip():
                raise ValueError(f"Record {index}: missing {key}")
        url = KnowledgeStore._validate_url(record["source_url"])
        normalized.append((url, record["title"].strip(), record["claim"].strip()))
    store = KnowledgeStore(db_path)
    created = 0
    seen = {(claim["claim"], tuple(
        (item["url"], item["relationship"]) for item in store.get_claim(claim["id"])["sources"]
    )) for claim in store.list_claims()}
    for url, title, claim in normalized:
        source = store.add_source(url, title)
        identity = (claim, ((url, "supports"),))
        if identity in seen:
            continue
        store.add_claim(claim, [source["id"]], status="unreviewed", confidence=0.5)
        seen.add(identity)
        created += 1
    return {"records": len(normalized), "new_unreviewed_claims": created}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", type=Path)
    parser.add_argument("--db", type=Path, default=Path("data/research_system.sqlite3"))
    args = parser.parse_args()
    records = json.loads(args.input_json.read_text(encoding="utf-8"))
    print(json.dumps(ingest_records(records, args.db), ensure_ascii=False))


if __name__ == "__main__":
    main()
