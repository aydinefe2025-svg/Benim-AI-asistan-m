"""Offline security and schema tests for the real public Crossref API connector."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import crossref_discovery as feed

GOOD = {'status': 'ok', 'message': {'items': [
    {'DOI': '10.1234/PAPER.A', 'title': ['<i>Biomimetic materials for soft robotics</i> <script>Title</script>'],
     'published': {'date-parts': [[2026, 11, 3]]}, 'type': 'journal-article'},
    {'DOI': '10.1234/PAPER.A', 'title': ['Duplicate title']},
    {'DOI': 'javascript:alert(1)', 'title': ['Bad DOI']},
]}}


class FakeResponse:
    def __init__(self, data, url, status=200):
        self.data, self.url, self.status = io.BytesIO(data), url, status
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, n):
        return self.data.read(n)
    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, raw, replace_url=None, status=200):
        self.raw, self.replace_url, self.status = raw, replace_url, status
        self.calls = []
    def open(self, req, timeout):
        self.calls.append((req.full_url, timeout))
        return FakeResponse(self.raw, self.replace_url or req.full_url, self.status)


class CrossrefDiscoveryTests(unittest.TestCase):
    def test_url_never_accepts_arbitrary_host(self):
        self.assertTrue(feed.build_url('robotics').startswith('https://api.crossref.org/works?'))
        for t in ('https://127.0.0.1/', 'evil', '', None):
            with self.assertRaises(ValueError):
                feed.build_url(t)
        for n in (0, 6, 10000, True, '5'):
            with self.assertRaises(ValueError):
                feed.build_url('robotics', n)

    def test_schema_pending_and_duplicate_doi(self):
        r = feed.parse_crossref_response(GOOD, 'robotics', '2026-11-04T00:00:00Z')
        self.assertEqual(len(r['items']), 1)
        self.assertEqual(r['items'][0]['doi'], '10.1234/paper.a')
        self.assertEqual(r['items'][0]['published'], '2026-11-03')
        self.assertEqual(r['items'][0]['review_status'], 'pending_review')
        self.assertFalse(r['claims_verified'])
        self.assertNotIn('<', r['items'][0]['title'])

    def test_hard_bad_response_fails(self):
        for r in ({}, {'status': 'fail', 'message': {}},
                  {'status': 'ok', 'message': {'items': 'none'}},
                  {'status': 'ok', 'message': {'items': []}}):
            with self.assertRaises(feed.FeedError):
                feed.parse_crossref_response(r, 'robotics')

    def test_overlong_response_rejected(self):
        fake = FakeOpener(b'x' * (feed.MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(feed.FeedError, 'too large'):
            feed.fetch_crossref('materials', opener=fake)

    def test_redirect_is_rejected_even_if_opener_misbehaves(self):
        fake = FakeOpener(json.dumps(GOOD).encode(), replace_url='http://127.0.0.1/secret')
        with self.assertRaisesRegex(feed.FeedError, 'redirected'):
            feed.fetch_crossref('robotics', opener=fake)

    def test_real_request_shape_but_mocked_transport(self):
        fake = FakeOpener(json.dumps(GOOD).encode())
        r = feed.fetch_crossref('materials', opener=fake)
        self.assertEqual(r['topic'], 'materials')
        self.assertEqual(len(r['items']), 1)
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0][1], 15)

    def test_malformed_json(self):
        with self.assertRaisesRegex(feed.FeedError, 'not JSON'):
            feed.fetch_crossref('history', opener=FakeOpener(b'{invalid'))

    def test_save_uses_temp_atomic_replacement(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'source.json'
            feed.save_json({'items': ['X']}, out)
            self.assertEqual(json.loads(out.read_text())['items'], ['X'])
            self.assertFalse((Path(d) / 'source.json.tmp').exists())

    def test_symlink_output_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'link.json'
            actual = Path(d) / 'actual.json'
            actual.write_text('original')
            out.symlink_to(actual)
            with self.assertRaisesRegex(feed.FeedError, 'unsafe'):
                feed.save_json({'x': 1}, out)
            self.assertEqual(actual.read_text(), 'original')

    def test_unrelated_results_must_not_enter_ai_queue(self):
        payload = {'status': 'ok', 'message': {'items': [
            {'DOI': '10.1234/unrelated', 'title': ['Spiritual intelligence and divorce']},
            {'DOI': '10.1234/real', 'title': ['Multi-agent artificial intelligence for scientific discovery']},
        ]}}
        records = feed.parse_crossref_response(payload, 'artificial_intelligence')
        self.assertEqual([item['doi'] for item in records['items']], ['10.1234/real'])
        self.assertEqual(records['relevance_policy'], 'topic_title_anchor')

    def test_all_irrelevant_rejected(self):
        payload = {'status': 'ok', 'message': {'items': [
            {'DOI': '10.1234/unrelated', 'title': ['Train tracks and heat waves']},
        ]}}
        with self.assertRaisesRegex(feed.FeedError, 'topic-relevant'):
            feed.parse_crossref_response(payload, 'artificial_intelligence')

    def test_bounded_search_prefers_relevance_over_date(self):
        url = feed.build_url('artificial_intelligence', 5)
        self.assertIn('sort=relevance', url)
        self.assertIn('filter=from-pub-date', url)

    def test_date_invalid_is_ignored(self):
        self.assertIsNone(feed.paper_date({'date-parts': [[2026, 13, 2]]}))
        self.assertIsNone(feed.paper_date({}))


if __name__ == '__main__':
    unittest.main()
