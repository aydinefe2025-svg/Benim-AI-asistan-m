import unittest
from urllib.parse import parse_qs, urlsplit
from core.scientific_sources import scientific_sources
from core.public_research import research_sources


class ScientificSourcesTests(unittest.TestCase):
    def test_relevance_dedup_attribution_and_unverified_status(self):
        def fetch(url):
            parsed = urlsplit(url)
            self.assertEqual(parsed.hostname, 'api.crossref.org')
            self.assertEqual(parse_qs(parsed.query)['sort'], ['relevance'])
            work = {'DOI': '10.1234/ABC', 'title': ['Z relevant'], 'score': 20,
                    'publisher': 'Research publisher', 'published': {'date-parts': [[2026, 1, 2]]}}
            return {'message': {'items': [work, work, {'DOI': '10.5678/def', 'title': ['A less relevant']}]}}
        found = scientific_sources('stellar physics', fetch=fetch)
        self.assertEqual([x['title'] for x in found], ['Z relevant', 'A less relevant'])
        self.assertEqual(found[0]['published_at'], '2026-01-02')
        self.assertEqual(found[0]['publisher'], 'Research publisher')
        self.assertFalse(any(x['verified'] for x in found))
        self.assertTrue(all(x['primary_source_review'] == 'required' for x in found))

    def test_malformed_metadata_cannot_invent_a_citation(self):
        bad = [{'DOI': 'https://evil.invalid', 'title': ['Fake']},
               {'DOI': '10.1234/x', 'title': []}, None]
        self.assertEqual(scientific_sources('x', fetch=lambda _: {'message': {'items': bad}}), [])
        with self.assertRaises(ValueError):
            scientific_sources('x', fetch=lambda _: {'message': {'items': 'not a list'}})

    def test_wikipedia_preserves_relevance_instead_of_alphabetical_order(self):
        pages = {'1': {'title': 'A', 'index': 2, 'fullurl': 'https://en.wikipedia.org/wiki/A'},
                 '2': {'title': 'Z', 'index': 1, 'fullurl': 'https://en.wikipedia.org/wiki/Z'}}
        self.assertEqual([x['title'] for x in research_sources('x', fetch=lambda _: {'query': {'pages': pages}})],
                         ['Z', 'A'])

    def test_turkish_research_request_uses_turkish_wikipedia_and_extracts_topic(self):
        def fetch(url):
            parsed = urlsplit(url)
            self.assertEqual(parsed.hostname, "tr.wikipedia.org")
            params = parse_qs(parsed.query)
            self.assertEqual(params["gsrsearch"], ["kütleçekimsel merceklenme"])
            return {"query": {"pages": {"1": {
                "title": "Kütleçekimsel merceklenme", "index": 1,
                "fullurl": "https://tr.wikipedia.org/wiki/K%C3%BCtle%C3%A7ekimsel_merceklenme",
            }}}}
        query = ("Araştır kütleçekimsel merceklenme. Bir Wikipedia kaynak pasajı bul; "
                 "yalnızca o pasajı özetle ve URL'sini ver.")
        found = research_sources(query, fetch=fetch)
        self.assertEqual(len(found), 1)
        self.assertTrue(found[0]["url"].startswith("https://tr.wikipedia.org/wiki/"))
