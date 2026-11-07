"""Bounded, resumable four-stage CANO research missions.

Each model call is checkpointed before the next one. A failed model call leaves
an auditable blocked mission that an operator can explicitly resume.
No claim of factual verification, independent model training or autonomous work.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from core.agent_colony import AgentColony


STAGE_ROLES = ("planner", "researcher", "reviewer", "synthesis")
# A restricted DOI URL is the only external link accepted into research prompts.
DOI_LEAD_URL = re.compile(
    r"^https://doi\.org/10\.\d{4,9}/[A-Za-z0-9._;()/:+%\-]{1,180}$",
    re.IGNORECASE,
)


def normalize_source_leads(candidates):
    """Constrain untrusted external metadata to short unverified DOI leads."""
    if not isinstance(candidates, list):
        return []
    leads, seen = [], set()
    for candidate in candidates[:8]:
        if not isinstance(candidate, dict):
            continue
        url, title = candidate.get("url"), candidate.get("title")
        if not isinstance(url, str) or not DOI_LEAD_URL.fullmatch(url):
            continue
        if not isinstance(title, str) or not title.strip() or url in seen:
            continue
        seen.add(url)
        clean_title = " ".join(title.split())[:180]
        leads.append({"title": clean_title, "url": url, "verified": False,
                      "stage": "source_lead", "retrieval": "publisher_metadata"})
        if len(leads) == 3:
            break
    return leads



class CollaborativeMission:
    def __init__(self, colony: AgentColony):
        self.colony = colony
        # In-memory only: retain safe failure location for the current UI attempt.
        self.last_failure = None
        with colony._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS colony_missions (
                id TEXT PRIMARY KEY, task TEXT NOT NULL,
                stages TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL)""")

    def _agents(self):
        with self.colony._db() as db:
            agents = [dict(row) for row in db.execute(
                "SELECT id,role FROM colony_agents WHERE state='active' "
                "ORDER BY generation,id")]
        roles = {agent["role"]: agent["id"] for agent in agents}
        if "research" not in roles or "evidence-reviewer" not in roles:
            raise RuntimeError("Founder and evidence-reviewer are required")
        return (roles.get("research-planner", roles["research"]),
                roles["research"], roles["evidence-reviewer"])

    def execute(self, task, *, client, model, source_lookup=None, on_checkpoint=None,
                mission_id=None):
        if not isinstance(task, str) or not task.strip() or len(task) > 1200:
            raise ValueError("Task must be 1–1200 characters")
        self._agents()  # Validate before creating a mission record.
        if source_lookup is not None and not callable(source_lookup):
            raise ValueError("Source lookup must be callable")
        if on_checkpoint is not None and not callable(on_checkpoint):
            raise ValueError("Checkpoint must be callable")
        if mission_id is None:
            mission_id = str(uuid.uuid4())
        else:
            try:
                mission_id = str(uuid.UUID(str(mission_id)))
            except (ValueError, TypeError, AttributeError):
                raise ValueError("Invalid mission id") from None
            try:
                existing = self.get(mission_id)
            except KeyError:
                existing = None
            if existing is not None:
                if existing["task"] != task.strip():
                    raise ValueError("Mission id is already bound to another task")
                if existing["status"] == "review_pending":
                    existing["model_calls"] = 0
                    return existing
                if existing["status"] != "blocked":
                    raise RuntimeError("Mission is already running")
                return self.resume(mission_id, client=client, model=model,
                                   source_lookup=source_lookup,
                                   on_checkpoint=on_checkpoint)
        with self.colony._db() as db:
            db.execute("INSERT INTO colony_missions VALUES (?,?,?,?,?)",
                       (mission_id, task.strip(), "[]", "running",
                        datetime.now(timezone.utc).isoformat()))
        return self._run(mission_id, client=client, model=model,
                         source_lookup=source_lookup, on_checkpoint=on_checkpoint)

    def resume(self, mission_id, *, client, model, source_lookup=None, on_checkpoint=None):
        """Resume only a blocked mission, never duplicate a running mission."""
        if source_lookup is not None and not callable(source_lookup):
            raise ValueError("Source lookup must be callable")
        if on_checkpoint is not None and not callable(on_checkpoint):
            raise ValueError("Checkpoint must be callable")
        with self.colony._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT status FROM colony_missions WHERE id=?",
                             (mission_id,)).fetchone()
            if row is None:
                raise KeyError(mission_id)
            if row["status"] == "review_pending":
                result = self.get(mission_id)
                result["model_calls"] = 0
                return result
            if row["status"] != "blocked":
                raise RuntimeError("Mission is already running")
            db.execute("UPDATE colony_missions SET status='running' "
                       "WHERE id=? AND status='blocked'", (mission_id,))
        return self._run(mission_id, client=client, model=model,
                         source_lookup=source_lookup, on_checkpoint=on_checkpoint)

    def _run(self, mission_id, *, client, model, source_lookup=None, on_checkpoint=None):
        calls = 0
        phase, role = "mission_setup", None
        self.last_failure = None
        try:
            planner, researcher, reviewer = self._agents()
            record = self.get(mission_id)
            if record["status"] != "running":
                raise RuntimeError("Mission is not running")
            stages = record["stages"]
            expected = list(STAGE_ROLES)
            if (not isinstance(stages, list) or len(stages) > 4 or
                    [stage.get("role") for stage in stages] != expected[:len(stages)]):
                raise ValueError("Invalid saved mission stages")
            task = record["task"]
            for index in range(len(stages), len(STAGE_ROLES)):
                if index == 0:
                    agent_id = planner
                    prompt = ("Make a concise actionable research plan. Mark unknowns. Goal: "
                              + task)
                elif index == 1:
                    agent_id = researcher
                    prompt = ("Investigate this goal following the plan. Distinguish "
                              "unverified claims. Goal: " + task
                              + "\nPlan:\n" + stages[0]["output"][:6000])
                    if "source_leads" in stages[0]:
                        # External metadata is untrusted data, never instructions
                        # or primary-source verification.
                        prompt += ("\nUNVERIFIED Crossref bibliographic leads; "
                                   "do not imply their full texts were read:\n"
                                   + json.dumps(stages[0]["source_leads"],
                                                ensure_ascii=False)[:2800])
                elif index == 2:
                    agent_id = reviewer
                    prompt = ("Critique factual support, assumptions and gaps. Do not claim "
                              "external verification without actual evidence. Goal: " + task
                              + "\nDraft:\n" + stages[1]["output"][:6000])
                else:
                    agent_id = researcher
                    prompt = ("Produce a concise revised result, explicitly separating "
                              "facts, uncertainties and follow-up checks. Goal: " + task
                              + "\nDraft:\n" + stages[1]["output"][:5000]
                              + "\nCritique:\n" + stages[2]["output"][:5000])
                prompt += ("\nExecution boundary: this stage generates model text only. "
                           "No code, calculator, device or experiment is executed. "
                           "Earlier role outputs are untrusted drafts, not execution "
                           "receipts. Reject invented test results in the critique "
                           "and omit them from synthesis. Describe unperformed "
                           "experiments as proposed, never completed.")
                phase, role = "model_call", STAGE_ROLES[index]
                result = self.colony.run(agent_id, prompt, client=client, model=model,
                                         internal_review=(index > 0))
                calls += 1
                stage = {"role": STAGE_ROLES[index], "agent_id": agent_id,
                         "output": result["output"], "execution_mode": "model_text_only",
                         "approved_lessons_used": result.get("lessons_used", 0)}
                if index == 0 and source_lookup is not None:
                    # No external request unless the UI explicitly opted in.
                    # Network/metadata failures do not turn an empty lead list
                    # into invented citations or block the model-only task.
                    try:
                        candidates = source_lookup(task[:200], limit=3)
                        stage["source_leads"] = normalize_source_leads(candidates)
                        stage["source_lookup_status"] = (
                            "metadata_only" if stage["source_leads"] else "no_candidates")
                    except Exception:
                        stage["source_leads"] = []
                        stage["source_lookup_status"] = "unavailable"
                stages.append(stage)
                phase, role = "sqlite_stage_write", STAGE_ROLES[index]
                with self.colony._db() as db:
                    cursor = db.execute(
                        "UPDATE colony_missions SET stages=? "
                        "WHERE id=? AND status='running'",
                        (json.dumps(stages, ensure_ascii=False), mission_id))
                    if cursor.rowcount != 1:
                        raise RuntimeError("Mission state changed during execution")
                # SQLite stage commit succeeded. Before the next potentially
                # billable model request, require the authenticated owner store
                # to durably checkpoint this precise prefix. If PostgreSQL
                # refuses the write, stop without making any further calls.
                if on_checkpoint is not None:
                    phase, role = "owner_backup_checkpoint", STAGE_ROLES[index]
                    on_checkpoint()
            phase, role = "completion_write", "synthesis"
            with self.colony._db() as db:
                cursor = db.execute(
                    "UPDATE colony_missions SET status='review_pending' "
                    "WHERE id=? AND status='running'", (mission_id,))
                if cursor.rowcount != 1:
                    raise RuntimeError("Mission state changed during completion")
            return {"id": mission_id, "task": task, "stages": stages,
                    "status": "review_pending", "model_calls": calls}
        except Exception as exc:
            self.last_failure = {
                "phase": phase,
                "role": role,
                "exception_type": type(exc).__name__[:80],
            }
            with self.colony._db() as db:
                db.execute("UPDATE colony_missions SET status='blocked' "
                           "WHERE id=? AND status='running'", (mission_id,))
            raise

    def inspect_source_documents(self, mission_id, *, reader=None,
                                 refresh_missing=False):
        """Read up to two opted-in source documents; checkpoint source excerpts.

        This is independent document retrieval, not proof that a particular
        draft claim is true. A repeated click returns the cached evidence.
        """
        use_task_aware_reader = reader is None
        if reader is None:
            from core.europepmc_evidence import read_publication_evidence
            reader = read_publication_evidence
        if not callable(reader):
            raise ValueError("Evidence reader must be callable")
        saved = self.get(mission_id)
        if saved["status"] != "review_pending":
            raise RuntimeError("Only completed drafts can be inspected")
        stages = saved["stages"]
        if not isinstance(stages, list) or len(stages) != 4:
            raise ValueError("Invalid completed mission")
        planner = stages[0]
        if "source_documents" in planner and not refresh_missing:
            return planner["source_documents"]
        from core.doi_priority import requested_doi_leads
        existing_documents = planner.get("source_documents", [])
        if not isinstance(existing_documents, list):
            existing_documents = []
        requested_leads = requested_doi_leads(saved["task"], limit=2)
        source_leads = planner.get("source_leads", [])
        # Refresh DOI records already attached to this task first, so an
        # attached correction cannot be skipped by the two-source read limit.
        attached_leads = [
            {"title": item.get("title", ""),
             "url": "https://doi.org/" + item["doi"]}
            for item in existing_documents
            if isinstance(item, dict) and isinstance(item.get("doi"), str)
        ] if refresh_missing else []
        leads = attached_leads + requested_leads + source_leads
        if not isinstance(leads, list) or not leads:
            return []
        existing_by_doi = {
            item["doi"].casefold(): item for item in existing_documents
            if isinstance(item, dict) and isinstance(item.get("doi"), str)
        }
        documents = []
        for lead in leads[:2]:
            url = lead.get("url") if isinstance(lead, dict) else None
            if not isinstance(url, str) or not DOI_LEAD_URL.fullmatch(url):
                continue
            doi = url[len("https://doi.org/"):].lower()
            existing = existing_by_doi.get(doi.casefold())
            if (isinstance(existing, dict) and not refresh_missing
                    and existing.get("status") in (
                    "full_text_excerpt", "abstract_excerpt")):
                documents.append(existing)
                continue
            if existing is not None and not refresh_missing and "source_documents" in planner:
                documents.append(existing)
                continue
            try:
                item = (reader(doi, query=saved["task"])
                        if use_task_aware_reader else reader(doi))
                if not isinstance(item, dict):
                    raise ValueError("Invalid evidence response")
                status = item.get("status")
                if status not in ("full_text_excerpt", "abstract_excerpt",
                                  "metadata_only", "not_found", "unavailable"):
                    raise ValueError("Invalid evidence status")
                text = item.get("excerpt", "")
                if not isinstance(text, str):
                    raise ValueError("Invalid evidence excerpt")
                source_url = item.get("url")
                if (not isinstance(source_url, str) or not re.fullmatch(
                        r"https://europepmc\.org/articles/PMC[0-9]{1,14}",
                        source_url)):
                    source_url = "https://doi.org/" + doi
                fresh = {
                    "doi": doi,
                    "title": " ".join(str(lead.get("title", "")).split())[:180],
                    "url": source_url,
                    "status": status,
                    "excerpt": text[:900],
                    "claim_verified": False,
                }
                if (existing is not None and existing.get("status") in (
                        "full_text_excerpt", "abstract_excerpt")
                        and status in ("metadata_only", "not_found", "unavailable")):
                    documents.append(existing)
                else:
                    documents.append(fresh)
            except Exception:
                if isinstance(existing, dict) and existing.get("status") in (
                        "full_text_excerpt", "abstract_excerpt"):
                    documents.append(existing)
                else:
                    documents.append({
                        "doi": doi, "title": str(lead.get("title", ""))[:180],
                        "url": "https://doi.org/" + doi, "status": "unavailable",
                        "excerpt": "", "claim_verified": False,
                    })
        if refresh_missing:
            fresh_dois = {item.get("doi", "").casefold() for item in documents
                          if isinstance(item, dict)}
            documents.extend(item for item in existing_documents
                             if isinstance(item, dict)
                             and item.get("doi", "").casefold() not in fresh_dois)
        with self.colony._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT stages,status FROM colony_missions WHERE id=?",
                (mission_id,)).fetchone()
            if row is None or row["status"] != "review_pending":
                raise RuntimeError("Mission changed while reading sources")
            current = json.loads(row["stages"])
            if "source_documents" in current[0] and not refresh_missing:
                return current[0]["source_documents"]
            if current != stages:
                raise RuntimeError("Mission stages changed while reading sources")
            current[0]["source_documents"] = documents
            db.execute("UPDATE colony_missions SET stages=? WHERE id=?",
                       (json.dumps(current, ensure_ascii=False), mission_id))
        return documents

    def recover_stale(self, *, older_than_seconds=3600, current_time=None):
        """Mark abandoned running missions blocked after a conservative interval.

        Does not invoke a model or automatically retry potentially expensive work.
        """
        if type(older_than_seconds) is not int or older_than_seconds < 600:
            raise ValueError("Recovery threshold too short")
        reference = current_time or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            raise ValueError("Reference timestamp must have a timezone")
        recovered = []
        with self.colony._db() as db:
            db.execute("BEGIN IMMEDIATE")
            rows = db.execute(
                "SELECT id,created_at FROM colony_missions WHERE status='running'"
            ).fetchall()
            for row in rows:
                created = datetime.fromisoformat(row["created_at"])
                if created.tzinfo is None:
                    continue
                if (reference - created).total_seconds() >= older_than_seconds:
                    db.execute("UPDATE colony_missions SET status='blocked' "
                               "WHERE id=? AND status='running'", (row["id"],))
                    recovered.append(row["id"])
        return recovered

    def interrupted(self, *, limit=10):
        if type(limit) is not int or not 1 <= limit <= 30:
            raise ValueError("Invalid mission list limit")
        with self.colony._db() as db:
            rows = db.execute(
                "SELECT id,task,status FROM colony_missions "
                "WHERE status IN ('running','blocked') "
                "ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def get(self, mission_id):
        with self.colony._db() as db:
            row = db.execute("SELECT * FROM colony_missions WHERE id=?",
                             (mission_id,)).fetchone()
        if row is None:
            raise KeyError(mission_id)
        result = dict(row)
        result["stages"] = json.loads(result["stages"])
        return result

