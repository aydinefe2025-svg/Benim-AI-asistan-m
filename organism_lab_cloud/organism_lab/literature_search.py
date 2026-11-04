"""Small, bounded OpenAlex literature lookup and provenance store.

Results are catalog metadata only. Finding a record does not verify its claims,
peer-review status, or full text.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.openalex.org/works"
MAX_QUERY_LENGTH = 200
MAX_RESULTS = 10
MAX_RESPONSE_BYTES = 2_000_000


def _valid_query(query: str) -> str:
    if not isinstance(query, str):
        raise ValueError("Search query must be text")
    query = " ".join(query.split())
    if not query or len(query) > MAX_QUERY_LENGTH:
        raise ValueError(f"Search query must contain 1–{MAX_QUERY_LENGTH} characters")
    return query


def _normalize_work(work: dict, retrieved_at: str) -> dict | None:
    if not isinstance(work, dict):
        return None
    work_id = work.get("id")
    title = work.get("title")
    if not isinstance(work_id, str) or not work_id.startswith("https://openalex.org/W"):
        return None
    if not isinstance(title, str) or not title.strip():
        return None
    work_type = work.get("type")
    is_retracted = work.get("is_retracted")
    # The UI is a literature-paper catalog, so exclude non-article records and
    # known retractions. OpenAlex metadata itself remains unverified.
    if work_type != "article" or is_retracted is not False:
        return None
    authors = []
    for authorship in work.get("authorships") or []:
        author = (authorship or {}).get("author") or {}
        name = author.get("display_name")
        if isinstance(name, str) and name.strip():
            authors.append(name.strip())
    primary = work.get("primary_location") or {}
    source = primary.get("source") or {}
    source_type = source.get("type")
    if source_type not in {"journal", "conference"}:
        return None
    doi = work.get("doi")
    return {
        "openalex_id": work_id,
        "title": title.strip(),
        "publication_year": work.get("publication_year"),
        "authors": authors,
        "doi": doi if isinstance(doi, str) else None,
        "landing_page_url": primary.get("landing_page_url"),
        "open_access_url": ((work.get("open_access") or {}).get("oa_url")),
        "venue": source.get("display_name"),
        "work_type": work_type,
        "source_type": source_type,
        "is_retracted": is_retracted,
        "retrieved_at": retrieved_at,
        "record_status": "catalog_metadata_unverified",
    }


def search_openalex(query: str, *, per_page: int = 5, opener=urlopen) -> list[dict]:
    """Fetch at most ten metadata records from the fixed OpenAlex API host."""
    query = _valid_query(query)
    if not isinstance(per_page, int) or isinstance(per_page, bool) or not 1 <= per_page <= MAX_RESULTS:
        raise ValueError(f"per_page must be between 1 and {MAX_RESULTS}")
    fetch_per_page = min(max(per_page * 10, 10), 50)
    params = urlencode({
        "search": query,
        "per-page": fetch_per_page,
        "select": "id,title,publication_year,authorships,doi,primary_location,open_access,type,is_retracted",
        "filter": "type:article,is_retracted:false",
    })
    request = Request(f"{API_URL}?{params}", headers={"User-Agent": "OrganismLab/1.0 (bounded literature metadata lookup)"})
    with opener(request, timeout=12) as response:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("OpenAlex response exceeded the size limit")
    document = json.loads(payload.decode("utf-8"))
    results = document.get("results") if isinstance(document, dict) else None
    if not isinstance(results, list):
        raise ValueError("OpenAlex response did not contain a results list")
    retrieved_at = datetime.now(timezone.utc).isoformat()
    normalized_results = []
    for item in results:
        normalized = _normalize_work(item, retrieved_at)
        if normalized is not None:
            normalized_results.append(normalized)
            if len(normalized_results) >= per_page:
                break
    return normalized_results


def save_records(output_dir: str | Path, query: str, records: list[dict]) -> int:
    """Upsert catalog metadata in the local research database; preserve provenance."""
    query = _valid_query(query)
    if len(records) > MAX_RESULTS:
        raise ValueError("Too many records")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "research_studies.sqlite3"
    saved = 0
    connection = sqlite3.connect(database)
    try:
        connection.execute("""CREATE TABLE IF NOT EXISTS literature_records (
            openalex_id TEXT PRIMARY KEY,
            query TEXT NOT NULL,
            title TEXT NOT NULL,
            publication_year INTEGER,
            authors_json TEXT NOT NULL,
            doi TEXT,
            landing_page_url TEXT,
            open_access_url TEXT,
            venue TEXT,
            retrieved_at TEXT NOT NULL,
            record_status TEXT NOT NULL,
            work_type TEXT,
            is_retracted INTEGER,
            source_type TEXT
        )""")
        existing_columns = {row[1] for row in connection.execute("PRAGMA table_info(literature_records)")}
        if "work_type" not in existing_columns:
            connection.execute("ALTER TABLE literature_records ADD COLUMN work_type TEXT")
        if "is_retracted" not in existing_columns:
            connection.execute("ALTER TABLE literature_records ADD COLUMN is_retracted INTEGER")
        if "source_type" not in existing_columns:
            connection.execute("ALTER TABLE literature_records ADD COLUMN source_type TEXT")
        for record in records:
            if record.get("record_status") != "catalog_metadata_unverified":
                raise ValueError("Literature records must remain marked unverified")
            cursor = connection.execute("""INSERT INTO literature_records
                (openalex_id, query, title, publication_year, authors_json, doi,
                 landing_page_url, open_access_url, venue, retrieved_at, record_status,
                 work_type, is_retracted, source_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(openalex_id) DO UPDATE SET
                  query=excluded.query, title=excluded.title,
                  publication_year=excluded.publication_year,
                  authors_json=excluded.authors_json, doi=excluded.doi,
                  landing_page_url=excluded.landing_page_url,
                  open_access_url=excluded.open_access_url, venue=excluded.venue,
                  retrieved_at=excluded.retrieved_at,
                  record_status=excluded.record_status,
                  work_type=excluded.work_type, is_retracted=excluded.is_retracted,
                  source_type=excluded.source_type""",
                (record["openalex_id"], query, record["title"], record.get("publication_year"),
                 json.dumps(record.get("authors", []), ensure_ascii=False), record.get("doi"),
                 record.get("landing_page_url"), record.get("open_access_url"),
                 record.get("venue"), record["retrieved_at"], record["record_status"],
                 record.get("work_type"), int(record["is_retracted"]) if record.get("is_retracted") is not None else None,
                 record.get("source_type")))
            saved += max(cursor.rowcount, 0)
        connection.commit()
    finally:
        connection.close()
    return saved


def list_records(output_dir: str | Path, *, limit: int = 50) -> list[dict]:
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    database = Path(output_dir) / "research_studies.sqlite3"
    if not database.exists():
        return []
    connection = sqlite3.connect(database)
    try:
        connection.row_factory = sqlite3.Row
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='literature_records'").fetchone()
        if not exists:
            return []
        rows = connection.execute("SELECT * FROM literature_records ORDER BY retrieved_at DESC LIMIT ?", (limit,)).fetchall()
    finally:
        connection.close()
    output = []
    for row in rows:
        item = dict(row)
        item["authors"] = json.loads(item.pop("authors_json"))
        if item.get("is_retracted") is not None:
            item["is_retracted"] = bool(item["is_retracted"])
        output.append(item)
    return output
