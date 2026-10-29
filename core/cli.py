"""Local CLI for tasks, research evidence, and local Ollama research runs.

Examples:
  python -m core.cli --db data/research.sqlite3 task-add "Audit a paper"
  python -m core.cli --db data/research.sqlite3 task-list
  python -m core.cli --db data/research.sqlite3 source-add https://example.org "Example paper"
  python -m core.cli --db data/research.sqlite3 research-run "Cezeri mekanizmalarının tarihsel etkisi"
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Sequence

from core.knowledge_store import KnowledgeStore
from core.ollama_client import OllamaClient
from core.research_orchestrator import ResearchOrchestrator
from core.task_store import TaskStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Büyük Sistem local task and research ledger")
    parser.add_argument("--db", default="data/research_system.sqlite3", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)

    task_add = sub.add_parser("task-add", help="Create a task")
    task_add.add_argument("title")
    task_add.add_argument("--goal", default="")

    task_list = sub.add_parser("task-list", help="List tasks")
    task_list.add_argument("--status", choices=["planned", "running", "blocked", "done", "verified"])

    task_transition = sub.add_parser("task-status", help="Change task status")
    task_transition.add_argument("task_id")
    task_transition.add_argument("status", choices=["planned", "running", "blocked", "done", "verified"])
    task_transition.add_argument("--note", default="")
    task_transition.add_argument("--evidence", action="append", default=[])
    task_transition.add_argument("--blocker", action="append", default=[])

    source_add = sub.add_parser("source-add", help="Record a source")
    source_add.add_argument("url")
    source_add.add_argument("title")
    source_add.add_argument("--publisher", default="")
    source_add.add_argument("--published-at", default="")
    source_add.add_argument("--content-file", help="Optional local text file to hash")
    source_add.add_argument("--notes", default="")

    claim_add = sub.add_parser("claim-add", help="Record a claim linked to source IDs")
    claim_add.add_argument("claim")
    claim_add.add_argument("--source-id", type=int, action="append", required=True)
    claim_add.add_argument("--status", choices=["unreviewed", "supported", "contested", "rejected"], default="unreviewed")
    claim_add.add_argument("--confidence", type=float, default=0.5)

    claim_list = sub.add_parser("claim-list", help="List claims")
    claim_list.add_argument("--status", choices=["unreviewed", "supported", "contested", "rejected"])

    research = sub.add_parser("research-run", help="Run planner, skeptic, and synthesis passes using local Ollama")
    research.add_argument("question")
    research.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    research.add_argument("--research-model", default=os.getenv("RUflo_RESEARCH_MODEL", ""))
    research.add_argument("--skeptic-model", default=os.getenv("RUflo_SKEPTIC_MODEL", ""))
    research.add_argument("--synthesis-model", default=os.getenv("RUflo_SYNTHESIS_MODEL", ""))
    research.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"))
    research.add_argument("--out", default="reports")
    return parser


def run(args: argparse.Namespace) -> object:
    tasks = TaskStore(args.db)
    knowledge = KnowledgeStore(args.db)

    if args.command == "task-add":
        return tasks.create(args.title, args.goal)
    if args.command == "task-list":
        return tasks.list(args.status)
    if args.command == "task-status":
        return tasks.transition(
            args.task_id, args.status, note=args.note,
            evidence=args.evidence, blockers=args.blocker if args.blocker else None,
        )
    if args.command == "source-add":
        content = ""
        if args.content_file:
            with open(args.content_file, "r", encoding="utf-8") as handle:
                content = handle.read()
        return knowledge.add_source(
            args.url, args.title, publisher=args.publisher,
            published_at=args.published_at, content=content, notes=args.notes,
        )
    if args.command == "claim-add":
        return knowledge.add_claim(
            args.claim, args.source_id, status=args.status, confidence=args.confidence
        )
    if args.command == "claim-list":
        return knowledge.list_claims(args.status)
    if args.command == "research-run":
        client = OllamaClient(args.ollama_url)
        available = client.list_models()
        model = args.research_model or args.model
        if model not in available:
            raise ValueError(f"Model '{model}' is not listed by Ollama. Installed models: {', '.join(available) or '(none)'}")
        result = ResearchOrchestrator(
            client, task_store=tasks, output_dir=args.out
        ).run(
            args.question,
            research_model=model,
            skeptic_model=args.skeptic_model or args.model,
            synthesis_model=args.synthesis_model or args.model,
        )
        result.pop("report", None)
        return result
    raise ValueError(f"Unsupported command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = run(args)
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
