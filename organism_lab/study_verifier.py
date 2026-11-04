"""Verify digital-genome study data by readback and independent recomputation.

A valid local receipt checks JSON, CSV and SQLite after a save. This is integrity
verification for a synthetic numerical model, not external scientific validation.
"""
import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from .reproduction_study import run_study

REPORT_FIELDS = ("schema", "design", "results", "observations", "interpretation_limits")


def verify_saved_study(saved):
    """Raise ValueError on missing, modified or inconsistent persisted study data.

    saved is a mapping containing study_id, json_path, csv_path, database_path.
    This reads all three storage formats rather than trusting a successful write.
    """
    try:
        identifier = saved["study_id"]
        json_path = Path(saved["json_path"])
        csv_path = Path(saved["csv_path"])
        database_path = Path(saved["database_path"])
        raw_json = json_path.read_bytes()
        document = json.loads(raw_json)
        if document.get("study_id") != identifier or not document.get("created_at"):
            raise ValueError("Study identity mismatch")
        design = document["design"]
        expected = run_study(
            seeds=tuple(design["seeds"]), steps=design["steps"],
            resource_levels=tuple(design["resource_levels_per_tick"]),
            capacity=design["capacity"], mutation_rate=design["mutation_rate"])
        if any(document.get(k) != expected[k] for k in REPORT_FIELDS):
            raise ValueError("Saved study differs from independently computed experiment")
        with csv_path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != list(expected["observations"][0]):
                raise ValueError("CSV columns differ from experimental observations")
            rows = list(reader)
        if rows != [{name: str(value) for name, value in row.items()}
                    for row in expected["observations"]]:
            raise ValueError("CSV observations differ from recomputed experiment")
        with sqlite3.connect(f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True) as conn:
            db_rows = conn.execute(
                "SELECT created_at, report_json, commentary_json FROM studies WHERE study_id=?",
                (identifier,)).fetchall()
        if len(db_rows) != 1:
            raise ValueError("Study missing or duplicated in SQLite")
        created_at, report_json, commentary_json = db_rows[0]
        if created_at != document["created_at"] or json.loads(report_json) != expected:
            raise ValueError("SQLite report or timestamp mismatch")
        if json.loads(commentary_json) != document["model_commentary"]:
            raise ValueError("SQLite commentary mismatch")
    except (OSError, KeyError, TypeError, IndexError, json.JSONDecodeError, sqlite3.Error) as exc:
        raise ValueError("Unable to read or validate saved study") from exc
    return {
        "verified": True, "study_id": identifier, "observations": len(expected["observations"]),
        "resource_levels": len(expected["results"]),
        "json_sha256": hashlib.sha256(raw_json).hexdigest(),
        "verified_files": ["json", "csv", "sqlite"],
        "verification": "readback-plus-independent-recomputation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("json_path", type=Path, help="Path to an exported study JSON file")
    options = parser.parse_args()
    doc = json.loads(options.json_path.read_text(encoding="utf-8"))
    path = options.json_path
    paths = {
        "study_id": doc["study_id"], "json_path": str(path),
        "csv_path": str(path.with_suffix(".csv")),
        "database_path": str(path.parent / "research_studies.sqlite3"),
    }
    print(json.dumps(verify_saved_study(paths), sort_keys=True))


if __name__ == "__main__":
    main()
