"""Network-free red/green tests for the bounded independent DOI check."""
import copy
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path

from crossref_live_audit import (
    AuditError, MAX_RESPONSE_BYTES, audit, parse_candidates, read_candidates, write_atomic,
)
from doi_evidence_gate import ISSUE_URL
from crossref_discovery import FeedError

DOI = '10.24963/ijcai.2025/538'
TITLE = 'Variational Offline Multi-agent Skill Discovery'
C = {'issue_comment_url': ISSUE_URL, 'items': [{'doi': DOI, 'title': TITLE}]}
M = {'status': 'ok', 'message': {'DOI': DOI, 'title': [TITLE], 'type': 'proceedings-article'}}


class Response:
    def __init__(self, data=None, url=None, status=200, content_type='application/json'):
        self.data = data if data is not None else json.dumps(M).encode()
        self.url = url
        self.status = status
        self.headers = {'Content-Type': content_type}

    def geturl(self):
        return self.url

    def read(self, n):
        return self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, data=None, status=200, code=None, redirect=False, content_type='application/json'):
        self.data, self.status, self.code, self.redirect, self.content_type = data, status, code, redirect, content_type
        self.urls = []

    def open(self, req, timeout=None):
        self.urls.append(req.full_url)
        assert timeout == 12
        if self.code is not None:
            raise urllib.error.HTTPError(req.full_url, self.code, 'error', None, None)
        payload = self.data
        if payload is None:
            doi = urllib.parse.unquote(req.full_url.split('/works/', 1)[1])
            payload = json.dumps({'status': 'ok', 'message': {'DOI': doi,
                'title': [TITLE if doi == DOI else 'AgenticSciML: collaborative multi-agent systems for emergent discovery in scientific machine learning'],
                'type': 'journal-article'}}).encode()
        return Response(payload, req.full_url + '/wrong' if self.redirect else req.full_url,
                        self.status, self.content_type)


class CrossrefLiveAuditTests(unittest.TestCase):
    def test_exact_match_no_scientific_claim(self):
        o = Opener()
        result = audit(C, opener=o, sleeper=lambda x: None, checked_at='2026-11-04')
        self.assertEqual(result['crossref_doi_title_matches'], 1)
        self.assertEqual(result['scientific_claims_reproduced'], 0)
        self.assertFalse(result['items'][0]['automated_acceptance'])
        self.assertTrue(o.urls[0].startswith('https://api.crossref.org/works/'))
        self.assertIn('%2F', o.urls[0])

    def test_not_found_does_not_fail_or_accept(self):
        result = audit(C, opener=Opener(code=404), sleeper=lambda x: None)
        self.assertEqual(result['items'][0]['crossref_status'], 'not_found_in_crossref')
        self.assertEqual(result['crossref_doi_title_matches'], 0)

    def test_different_title_not_matched(self):
        data = json.dumps({'status': 'ok', 'message': dict(M['message'], title=['Other Completely Different Title'])}).encode()
        r = audit(C, opener=Opener(data=data), sleeper=lambda x: None)
        self.assertEqual(r['items'][0]['crossref_status'], 'crossref_title_disagrees')
        self.assertEqual(r['scientific_claims_reproduced'], 0)

    def test_crossref_wrong_doi_fails(self):
        data = json.dumps({'status': 'ok', 'message': dict(M['message'], DOI='10.9999/unrelated')}).encode()
        with self.assertRaises(AuditError): audit(C, opener=Opener(data=data))

    def test_invalid_json_fails(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(data=b'<html>no</html>'))

    def test_invalid_content_type_fails(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(content_type='text/html'))

    def test_too_large_fails(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(data=b'x' * (MAX_RESPONSE_BYTES + 5)))

    def test_redirect_fails(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(redirect=True))

    def test_redirect_handler_error_is_safe(self):
        class RedirOpener:
            def open(self, request, timeout=12):
                raise FeedError("fake redirect")
        with self.assertRaises(AuditError): audit(C, opener=RedirOpener())

    def test_rate_limit_fails_no_partial_output(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(code=429))

    def test_other_http_failure(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(code=503))

    def test_envelope_mismatch_fails(self):
        with self.assertRaises(AuditError): audit(C, opener=Opener(data=b'{"status":"error","message":{}}'))

    def test_duplicate_candidate_fails(self):
        c = copy.deepcopy(C)
        c['items'].append(c['items'][0])
        with self.assertRaises(AuditError): parse_candidates(c)

    def test_candidate_url_rejects_injected_host(self):
        c = copy.deepcopy(C)
        c['issue_comment_url'] = 'https://evil.example/164'
        with self.assertRaises(AuditError): parse_candidates(c)

    def test_serial_throttle(self):
        c = {'issue_comment_url': ISSUE_URL, 'items': [C['items'][0], {
            'doi': '10.1038/s44387-026-00102-5', 'title': 'AgenticSciML: collaborative multi-agent systems for emergent discovery in scientific machine learning'}]}
        pauses = []
        o = Opener()
        r = audit(c, opener=o, sleeper=pauses.append)
        self.assertEqual(r['records_checked'], 2)
        self.assertEqual(len(pauses), 1)
        self.assertGreaterEqual(pauses[0], 0.25)

    def test_atomic_output_and_replay(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'report.json'
            r = audit(C, opener=Opener(), checked_at='fixed')
            write_atomic(r, path)
            b = path.read_bytes()
            write_atomic(r, path)
            self.assertEqual(path.read_bytes(), b)
            self.assertFalse((Path(d) / 'report.json.tmp').exists())

    def test_oversize_input_fails(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.json'
            p.write_bytes(b' ' * 17000)
            with self.assertRaises(AuditError): read_candidates(p)

    def test_atomic_preexisting_temp_fails_without_overwriting(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'report.json'
            t = Path(d) / 'report.json.tmp'
            p.write_text('PREVIOUS')
            t.write_text('OTHER')
            with self.assertRaises(FileExistsError): write_atomic({'x': 1}, p)
            self.assertEqual(p.read_text(), 'PREVIOUS')
            self.assertEqual(t.read_text(), 'OTHER')


if __name__ == '__main__':
    unittest.main()
