"""Model proposals require verbatim, authenticated source excerpts before citation."""
import json
import tempfile
import unittest
from pathlib import Path

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission
from core.claim_evidence import audit_claim_quotes


DOI = "10.1038/nprot.2013.143"
QUOTE = "Targeted nucleases are powerful tools for genome engineering."


class DraftModel:
    def chat(self, model, system, prompt):
        return "Draft needs evidence; claims are not verified."


class QuoteModel:
    def __init__(self, claims):
        self.calls = []
        self.claims = claims

    def chat(self, model, system, prompt):
        self.calls.append((model, system, prompt))
        return json.dumps({"claims": self.claims}, ensure_ascii=False)


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

    def test_verbatim_excerpt_quote_is_cited_but_never_fact_verified(self):
        self.add_excerpt()
        model = QuoteModel([
            {"claim": "Targeted nucleases are powerful genome tools",
             "doi": DOI.upper(), "quote": QUOTE}])
        result = audit_claim_quotes(self.manager, self.mission_id,
                                    client=model, model="configured-provider")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "quote_found_unverified")
        self.assertEqual(result[0]["doi"], DOI)
        self.assertEqual(result[0]["citation_url"],
                         "https://europepmc.org/articles/PMC1234567")
        self.assertEqual(result[0]["quote"], QUOTE)
        self.assertFalse(result[0]["claim_verified"])
        self.assertEqual(len(model.calls), 1)
        self.assertIn("abstract_excerpt", model.calls[0][2])
        saved = CollaborativeMission(self.manager.colony).get(self.mission_id)
        self.assertEqual(saved["stages"][0]["source_claim_audit"], result)
        again = audit_claim_quotes(self.manager, self.mission_id,
                                   client=model, model="configured-provider")
        self.assertEqual(again, result)
        self.assertEqual(len(model.calls), 1)

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
        got = audit_claim_quotes(
            self.manager, self.mission_id,
            client=QuoteModel([{"claim": "Nucleases were used", "doi": DOI,
                                "quote": QUOTE}]), model="stub")
        self.assertEqual(got[0]["status"], "quote_not_found")
        self.assertIsNone(got[0]["citation_url"])

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
        record = self.manager.execute(
            "Explicitly inspect DOI " + DOI + " and distinguish other studies",
            client=DraftModel(), model="stub",
            source_lookup=lambda q, limit=3: [
                {"title":"Unrelated A","url":"https://doi.org/10.7777/a"},
                {"title":"Unrelated B","url":"https://doi.org/10.7777/b"},
                {"title":"Unrelated C","url":"https://doi.org/10.7777/c"}])
        leads = record["stages"][0]["source_leads"]
        self.assertEqual(leads[0]["url"], "https://doi.org/" + DOI)
        self.assertEqual(len(leads), 3)
        self.assertFalse(leads[0]["verified"])


if __name__ == "__main__":
    unittest.main()
