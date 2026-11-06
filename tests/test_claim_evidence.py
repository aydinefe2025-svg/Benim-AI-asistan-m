"""Model proposals require verbatim, authenticated source excerpts before citation."""
import json
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission
from core.claim_evidence import (
    audit_claim_quotes, has_readable_source_excerpt, record_source_claim_review,
)
from core.targeted_research import execute_targeted_research


DOI = "10.1038/nprot.2013.143"
QUOTE = "Targeted nucleases are powerful tools for genome engineering."


class ReviewQueueFilterTests(unittest.TestCase):
    def test_includes_only_safe_readable_source_excerpts(self):
        readable = [{
            "source_documents": [{
                "status": "abstract_excerpt",
                "doi": DOI,
                "url": "https://europepmc.org/articles/PMC1234567",
                "excerpt": "An actual abstract excerpt.",
            }],
        }]
        self.assertTrue(has_readable_source_excerpt(readable))
        self.assertTrue(has_readable_source_excerpt(json.dumps(readable)))

    def test_excludes_metadata_only_missing_and_unsafe_sources(self):
        cases = [
            [{"source_documents": [{
                "status": "metadata_only", "doi": DOI,
                "url": "https://doi.org/" + DOI, "excerpt": QUOTE,
            }]}],
            [{"source_documents": [{
                "status": "full_text_excerpt", "doi": DOI,
                "url": "https://doi.org/" + DOI, "excerpt": "  ",
            }]}],
            [{"source_documents": [{
                "status": "full_text_excerpt", "doi": DOI,
                "url": "http://doi.org/" + DOI, "excerpt": QUOTE,
            }]}],
            [{"source_documents": [{
                "status": "full_text_excerpt", "doi": "not-a-doi",
                "url": "https://doi.org/not-a-doi", "excerpt": QUOTE,
            }]}],
            [{"source_documents": []}],
            [],
            "not-json",
        ]
        for stages in cases:
            with self.subTest(stages=stages):
                self.assertFalse(has_readable_source_excerpt(stages))


class DraftModel:
    def chat(self, model, system, prompt):
        return "Draft needs evidence; claims are not verified."


class QuoteModel:
    def __init__(self, claims):
        self.calls = []
        self.claims = claims
        self.verdict = "supported"

    def chat(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        return json.dumps({"claims": self.claims}, ensure_ascii=False)

    def verify(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        candidates = json.loads(prompt.split("\n", 1)[1])
        return json.dumps({"assessments": [
            {"index": item["index"], "verdict": self.verdict,
             "reason": "The passage was checked against the claim."}
            for item in candidates
        ]})


class ClaimQuoteAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        colony = AgentColony(Path(self.tmp.name) / "colony.sqlite3")
        colony.create_founder("research", "Research")
        colony.grow_specialists(approved=True)
        self.manager = CollaborativeMission(colony)
        record = self.manager.execute(
            "Read Ran et al DOI " + DOI, client=DraftModel(), model="stub",
            source_lookup=lambda q, limit=3: [
                {"title": "Genome engineering", "url": "https://doi.org/" + DOI}])
        self.mission_id = record["id"]

    def add_excerpt(self):
        return self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {
                "doi": doi, "status": "abstract_excerpt",
                "title": "Genome engineering",
                "url": "https://europepmc.org/articles/PMC1234567",
                "excerpt": QUOTE + " Other methods were evaluated.",
                "claim_verified": False})

    def test_refresh_missing_sources_adds_requested_dois_without_losing_good_evidence(self):
        with self.manager.colony._db() as db:
            row = db.execute("SELECT stages FROM colony_missions WHERE id=?",
                             (self.mission_id,)).fetchone()
            stages = json.loads(row[0])
            stages[0]["source_leads"] = [
                {"title": "Wrong match", "url": "https://doi.org/10.64239/pi-tr-qt4802"},
                {"title": "Correction", "url": "https://doi.org/10.1136/bmj.q1024"},
            ]
            db.execute("UPDATE colony_missions SET task=?,stages=? WHERE id=?",
                       ("BMJ paper 10.1136/bmj-2023-075847; correction 10.1136/bmj.q1024",
                        json.dumps(stages), self.mission_id))
        old = self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {"doi": doi, "status": "not_found", "title": "",
                                "url": "https://doi.org/" + doi, "excerpt": ""})
        self.assertEqual(old[0]["doi"], "10.1136/bmj-2023-075847")
        retained = []
        def reader(doi):
            retained.append(doi)
            return {"doi": doi, "status": "full_text_excerpt", "title": "BMJ paper",
                    "url": "https://europepmc.org/articles/PMC1234567",
                    "excerpt": "Retrieved paper excerpt.", "claim_verified": False}
        refreshed = self.manager.inspect_source_documents(
            self.mission_id, reader=reader, refresh_missing=True)
        self.assertIn("10.1136/bmj-2023-075847", retained)
        self.assertEqual(refreshed[0]["status"], "full_text_excerpt")
        saved = self.manager.get(self.mission_id)["stages"][0]["source_documents"]
        self.assertEqual(saved, refreshed)

    def test_refresh_reloads_attached_correction_even_when_not_a_task_doi(self):
        correction = "10.1136/bmj.q1024"
        with self.manager.colony._db() as db:
            row = db.execute("SELECT stages FROM colony_missions WHERE id=?",
                             (self.mission_id,)).fetchone()
            stages = json.loads(row[0])
            stages[0]["source_documents"] = [
                {"doi": DOI, "title": "BMJ article", "url": "https://doi.org/" + DOI,
                 "status": "full_text_excerpt", "excerpt": "Old article", "claim_verified": False},
                {"doi": correction, "title": "BMJ correction",
                 "url": "https://doi.org/" + correction,
                 "status": "full_text_excerpt", "excerpt": "Old correction", "claim_verified": False},
            ]
            stages[0]["source_leads"] = []
            db.execute("UPDATE colony_missions SET task=?,stages=? WHERE id=?",
                       ("Review BMJ paper " + DOI, json.dumps(stages), self.mission_id))

        read = []
        def reader(doi):
            read.append(doi)
            return {"doi": doi, "status": "full_text_excerpt", "title": "BMJ",
                    "url": "https://europepmc.org/articles/PMC1234567",
                    "excerpt": "Fresh " + doi, "claim_verified": False}

        refreshed = self.manager.inspect_source_documents(
            self.mission_id, reader=reader, refresh_missing=True)
        self.assertEqual(read, [DOI, correction])
        self.assertEqual([item["excerpt"] for item in refreshed],
                         ["Fresh " + DOI, "Fresh " + correction])

    def test_verbatim_excerpt_quote_is_cited_but_never_fact_verified(self):
        self.add_excerpt()
        model = QuoteModel([
            {"claim": "Targeted nucleases are powerful genome tools",
             "doi": DOI.upper(), "quote": QUOTE,
             "comparison": "supports",
             "rationale": "The exact passage makes the same bounded statement."}])
        result = audit_claim_quotes(self.manager, self.mission_id,
                                    client=model, model="configured-provider")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "quote_found_unverified")
        self.assertEqual(result[0]["doi"], DOI)
        self.assertEqual(result[0]["citation_url"],
                         "https://europepmc.org/articles/PMC1234567")
        self.assertEqual(result[0]["quote"], QUOTE)
        self.assertFalse(result[0]["claim_verified"])
        self.assertEqual(result[0]["comparison"], "supports")
        self.assertEqual(result[0]["comparison_status"], "model_suggested")
        self.assertEqual(
            result[0]["comparison_rationale"],
            "The exact passage makes the same bounded statement.")
        self.assertIn("central testable claim", model.calls[0][1])
        self.assertIn("secondary to the task", model.calls[0][2])
        self.assertEqual(result[0]["machine_assessment"]["verdict"], "supported")
        self.assertEqual(len(model.calls), 2)
        self.assertIn("abstract_excerpt", model.calls[0][2])
        saved = CollaborativeMission(self.manager.colony).get(self.mission_id)
        self.assertEqual(saved["stages"][0]["source_claim_audit"], result)
        again = audit_claim_quotes(self.manager, self.mission_id,
                                   client=model, model="configured-provider")
        self.assertEqual(again, result)
        self.assertEqual(len(model.calls), 2)


    def test_skeptical_verdict_never_marks_claim_verified(self):
        self.add_excerpt()
        model = QuoteModel([{
            "claim": "A stronger claim than the cited passage",
            "doi": DOI, "quote": QUOTE,
            "comparison": "contradicts",
            "rationale": "The statement exceeds the passage.",
        }])
        model.verdict = "contradicted"
        result = audit_claim_quotes(self.manager, self.mission_id,
                                    client=model, model="stub")
        self.assertEqual(result[0]["machine_assessment"]["verdict"], "contradicted")
        self.assertEqual(result[0]["status"], "quote_found_unverified")
        self.assertFalse(result[0]["claim_verified"])


    def test_failed_skeptical_pass_keeps_deterministic_quote_audit(self):
        self.add_excerpt()
        model = QuoteModel([{
            "claim": "A claim", "doi": DOI, "quote": QUOTE,
            "comparison": "supports", "rationale": "proposal",
        }])

        def unavailable(*_args):
            raise RuntimeError("provider detail must not leak")

        model.verify = unavailable
        result = audit_claim_quotes(self.manager, self.mission_id,
                                    client=model, model="stub")
        self.assertEqual(result[0]["status"], "quote_found_unverified")
        self.assertFalse(result[0]["claim_verified"])
        self.assertFalse(result[0]["machine_assessment"]["available"])
        saved = CollaborativeMission(self.manager.colony).get(self.mission_id)
        self.assertEqual(saved["stages"][0]["source_claim_audit"], result)


    def test_legacy_audit_is_preserved_when_upgraded_and_new_version_is_idempotent(self):
        self.add_excerpt()
        legacy = [{
            "claim": "Legacy descriptive claim",
            "doi": DOI,
            "quote": QUOTE,
            "status": "quote_found_unverified",
            "citation_url": "https://europepmc.org/articles/PMC1234567",
            "claim_verified": False,
        }]
        stages = self.manager.get(self.mission_id)["stages"]
        stages[0]["source_claim_audit"] = legacy
        with self.manager.colony._db() as db:
            db.execute("UPDATE colony_missions SET stages=? WHERE id=?",
                       (json.dumps(stages), self.mission_id))

        model = QuoteModel([{
            "claim": "Targeted nucleases are powerful genome tools",
            "doi": DOI,
            "quote": QUOTE,
            "comparison": "supports",
            "rationale": "The quoted passage makes this bounded statement.",
        }])
        upgraded = audit_claim_quotes(self.manager, self.mission_id,
                                      client=model, model="stub")
        saved_stage = self.manager.get(self.mission_id)["stages"][0]
        self.assertEqual(saved_stage["source_claim_audit_version"], 3)
        self.assertEqual(saved_stage["source_claim_audit"], upgraded)
        self.assertEqual(
            saved_stage["source_claim_audit_history"],
            [{"version": 1, "claims": legacy}],
        )
        self.assertEqual(upgraded[0]["comparison"], "supports")
        self.assertEqual(upgraded[0]["machine_assessment"]["verdict"], "supported")
        self.assertFalse(upgraded[0]["claim_verified"])

        class MustNotCall:
            def chat(self, model, system, prompt):
                raise AssertionError("Version 2 audit should be idempotent")

        self.assertEqual(
            audit_claim_quotes(self.manager, self.mission_id,
                               client=MustNotCall(), model="stub"),
            upgraded,
        )
        self.assertEqual(len(model.calls), 2)


    def test_unmatched_quote_can_be_retried_and_previous_audit_is_preserved(self):
        self.add_excerpt()
        bad = QuoteModel([{
            "claim": "In adults with major depression, exercise reduces depression symptoms.",
            "doi": DOI,
            "quote": "A fabricated quote that is not in the source.",
            "comparison": "supports",
            "rationale": "The model says it is supported.",
        }])
        first = audit_claim_quotes(self.manager, self.mission_id, client=bad, model="stub")
        self.assertEqual(first[0]["status"], "quote_not_found")
        self.assertEqual(first[0]["comparison"], "insufficient")
        self.assertFalse(first[0]["claim_verified"])

        retry = QuoteModel([{
            "claim": "In adults with major depression, exercise reduces depression symptoms.",
            "doi": DOI,
            "quote": QUOTE,
            "comparison": "supports",
            "rationale": "The exact source passage supports this bounded claim.",
        }])
        second = audit_claim_quotes(self.manager, self.mission_id,
                                    client=retry, model="stub")
        stage = self.manager.get(self.mission_id)["stages"][0]
        self.assertEqual(second[0]["status"], "quote_found_unverified")
        self.assertEqual(second[0]["comparison"], "supports")
        self.assertFalse(second[0]["claim_verified"])
        self.assertEqual(stage["source_claim_audit_version"], 3)
        self.assertEqual(stage["source_claim_audit_history"],
                         [{"version": 3, "claims": first}])
        self.assertEqual(len(bad.calls), 1)
        self.assertEqual(len(retry.calls), 2)
        self.assertIn("exact words and punctuation", retry.calls[0][1])

    def test_unmatched_quote_cannot_present_a_model_relation_as_evidence(self):
        self.add_excerpt()
        model = QuoteModel([{
            "claim": "A claim not supported by this excerpt",
            "doi": DOI, "quote": "A fabricated quote that is not in the source.",
            "comparison": "supports",
            "rationale": "The model says it is supported.",
        }])
        got = audit_claim_quotes(self.manager, self.mission_id,
                                 client=model, model="stub")
        self.assertEqual(got[0]["status"], "quote_not_found")
        self.assertEqual(got[0]["comparison"], "insufficient")
        self.assertEqual(got[0]["comparison_status"], "not_assessed")
        self.assertFalse(got[0]["claim_verified"])

    def test_quote_outside_supplied_excerpt_is_not_cited(self):
        self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {
                "doi": doi, "status": "full_text_excerpt",
                "url": "https://doi.org/" + doi,
                "excerpt": QUOTE,
                "claim_verified": False})
        stages = self.manager.get(self.mission_id)["stages"]
        stages[0]["source_documents"][0]["excerpt"] = "intro " * 160 + QUOTE
        with self.manager.colony._db() as db:
            db.execute("UPDATE colony_missions SET stages=? WHERE id=?",
                       (json.dumps(stages), self.mission_id))
        model = QuoteModel([{"claim": "A claim", "doi": DOI, "quote": QUOTE}])
        result = audit_claim_quotes(self.manager, self.mission_id,
                                    client=model, model="stub")
        self.assertNotIn(QUOTE, model.calls[0][2])
        self.assertEqual(result[0]["status"], "quote_not_found")
        self.assertIsNone(result[0]["citation_url"])

    def test_hallucinated_quote_or_doi_cannot_be_validated(self):
        self.add_excerpt()
        model = QuoteModel([
            {"claim": "Nucleases were harmless in humans", "doi": DOI,
             "quote": "Clinical studies prove no human off-target effects."},
            {"claim": "Mice were cured", "doi": "10.9999/invented",
             "quote": QUOTE},
        ])
        got = audit_claim_quotes(self.manager, self.mission_id,
                                 client=model, model="stub")
        self.assertEqual(len(got), 2)
        self.assertTrue(all(row["status"] == "quote_not_found" for row in got))
        self.assertTrue(all(not row["claim_verified"] for row in got))
        self.assertTrue(all(row["citation_url"] is None for row in got))

    def test_metadata_only_source_never_gives_quote_proof(self):
        self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {
                "doi": doi, "status": "metadata_only", "excerpt": QUOTE,
                "url": "https://doi.org/" + doi, "claim_verified": False})
        model = QuoteModel([{"claim": "Nucleases were used", "doi": DOI,
                             "quote": QUOTE}])
        # Metadata cannot support a quote: reject before spending provider calls.
        with self.assertRaises(ValueError):
            audit_claim_quotes(self.manager, self.mission_id,
                               client=model, model="stub")
        self.assertEqual(model.calls, [])

    def test_refuses_to_spend_model_call_when_no_source_excerpt(self):
        model = QuoteModel([{"claim": "Something", "doi": DOI, "quote": QUOTE}])
        with self.assertRaises(ValueError):
            audit_claim_quotes(self.manager, self.mission_id,
                               client=model, model="stub")
        self.assertEqual(model.calls, [])

    def test_invalid_json_is_neither_accepted_nor_stored(self):
        self.add_excerpt()
        class Invalid:
            def chat(self, model, system, prompt):
                return "A citation exists, trust me!"
        with self.assertRaises(ValueError):
            audit_claim_quotes(self.manager, self.mission_id,
                               client=Invalid(), model="stub")
        stages = self.manager.get(self.mission_id)["stages"]
        self.assertNotIn("source_claim_audit", stages[0])

    def test_strict_limit_of_three_audited_claims_and_bounded_prompt(self):
        self.add_excerpt()
        entries = [{"claim": "Claim " + str(i) + " about molecular tools",
                    "doi": DOI, "quote": QUOTE} for i in range(8)]
        model = QuoteModel(entries)
        got = audit_claim_quotes(self.manager, self.mission_id,
                                 client=model, model="stub")
        self.assertEqual(len(got), 3)
        self.assertLessEqual(len(model.calls[0][2]), 6200)
        self.assertTrue(all(row["claim_verified"] is False for row in got))

    def test_requested_doi_wins_over_unrelated_crossref_candidates(self):
        record = execute_targeted_research(
            self.manager,
            "Explicitly inspect DOI " + DOI + " and distinguish other studies",
            client=DraftModel(), model="stub",
            lookup=lambda q, limit=3: [
                {"title":"Unrelated A","url":"https://doi.org/10.7777/a"},
                {"title":"Unrelated B","url":"https://doi.org/10.7777/b"},
                {"title":"Unrelated C","url":"https://doi.org/10.7777/c"}])
        leads = record["stages"][0]["source_leads"]
        self.assertEqual(leads[0]["url"], "https://doi.org/" + DOI)
        self.assertEqual(len(leads), 3)
        self.assertFalse(leads[0]["verified"])


    def test_authenticated_full_text_review_verifies_only_the_claim_and_persists_audit(self):
        self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {
                "doi": doi, "status": "full_text_excerpt",
                "title": "Original research",
                "url": "https://europepmc.org/articles/PMC1234567",
                "excerpt": QUOTE + " Study results follow.",
                "claim_verified": False})
        model = QuoteModel([{"claim": "Targeted nucleases are powerful genome tools",
                             "doi": DOI, "quote": QUOTE}])
        audit_claim_quotes(self.manager, self.mission_id, client=model, model="stub")
        reviewer = "oidc_" + "a" * 64
        with self.assertRaises(ValueError):
            record_source_claim_review(
                self.manager, self.mission_id, 0, reviewer_id=reviewer,
                supported=True, rationale="The article supports this result.",
                primary_source_confirmed=False)
        with self.assertRaises(PermissionError):
            record_source_claim_review(
                self.manager, self.mission_id, 0, reviewer_id="reviewer",
                supported=True, rationale="The article supports this result.",
                primary_source_confirmed=True)
        result = record_source_claim_review(
            self.manager, self.mission_id, 0, reviewer_id=reviewer,
            supported=True,
            rationale="The full-text results directly support this specific claim.",
            primary_source_confirmed=True)
        self.assertTrue(result["claim_verified"])
        self.assertEqual(result["human_review"]["status"], "human_reviewed_supported")
        self.assertEqual(result["human_review"]["reviewer_id"], reviewer)
        mission = self.manager.get(self.mission_id)
        self.assertEqual(mission["status"], "review_pending")
        events = mission["stages"][0]["source_claim_review_events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["evidence_digest"], result["human_review"]["evidence_digest"])

    def test_abstract_or_unmatched_quote_cannot_be_accepted_but_can_be_rejected(self):
        self.add_excerpt()
        model = QuoteModel([{"claim": "Targeted nucleases are powerful genome tools",
                             "doi": DOI, "quote": QUOTE}])
        audit_claim_quotes(self.manager, self.mission_id, client=model, model="stub")
        with self.assertRaises(ValueError):
            record_source_claim_review(
                self.manager, self.mission_id, 0,
                reviewer_id="oidc_" + "b" * 64, supported=True,
                rationale="An abstract is not enough for primary-source review.",
                primary_source_confirmed=True)
        result = record_source_claim_review(
            self.manager, self.mission_id, 0,
            reviewer_id="oidc_" + "b" * 64, supported=False,
            rationale="The abstract does not establish this specific claim.",
            primary_source_confirmed=False)
        self.assertFalse(result["claim_verified"])
        self.assertEqual(result["human_review"]["status"], "human_reviewed_not_supported")
        self.assertEqual(self.manager.get(self.mission_id)["status"], "review_pending")

    def test_human_acceptance_cannot_use_a_changed_or_mismatched_source(self):
        self.manager.inspect_source_documents(
            self.mission_id,
            reader=lambda doi: {
                "doi": doi, "status": "full_text_excerpt",
                "url": "https://europepmc.org/articles/PMC1234567",
                "excerpt": "A different passage that does not match the proposed quotation.",
                "claim_verified": False})
        model = QuoteModel([{"claim": "Unsupported claim", "doi": DOI, "quote": QUOTE}])
        audit_claim_quotes(self.manager, self.mission_id, client=model, model="stub")
        with self.assertRaises(ValueError):
            record_source_claim_review(
                self.manager, self.mission_id, 0,
                reviewer_id="oidc_" + "c" * 64, supported=True,
                rationale="The full-text data directly support this claim.",
                primary_source_confirmed=True)
        result = record_source_claim_review(
            self.manager, self.mission_id, 0,
            reviewer_id="oidc_" + "c" * 64, supported=False,
            rationale="The quoted passage is absent from the retrieved text.",
            primary_source_confirmed=False)
        self.assertFalse(result["claim_verified"])
        self.assertEqual(result["human_review"]["status"], "human_reviewed_not_supported")


if __name__ == "__main__":
    unittest.main()
