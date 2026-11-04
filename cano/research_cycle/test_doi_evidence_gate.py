import copy
import json
import tempfile
import unittest
from pathlib import Path
from doi_evidence_gate import EvidenceError, ISSUE_URL, verify, read_limited_json, main


CANDIDATES = {'issue_comment_url': ISSUE_URL, 'items': [
    {'doi': '10.1038/s44387-026-00102-5', 'title': 'AgenticSciML: collaborative multi-agent systems for emergent discovery in scientific machine learning'},
]}
EVIDENCE = {'evidence': [
    {'doi': '10.1038/s44387-026-00102-5',
     'source_title': 'AgenticSciML: collaborative multi-agent systems for emergent discovery in scientific machine learning',
     'url': 'https://www.nature.com/articles/s44387-026-00102-5',
     'source_kind': 'publisher', 'observation_method': 'web_source_inspection', 'science_reproduced': False}
]}


class TestEvidenceGate(unittest.TestCase):
    def test_publishers_match_metadata_not_science(self):
        r = verify(CANDIDATES, EVIDENCE)
        self.assertEqual(r['bibliographic_matches'], 1)
        self.assertEqual(r['scientific_claims_verified'], 0)
        self.assertEqual(r['items'][0]['bibliographic_status'], 'publisher_metadata_match')
        self.assertFalse(r['items'][0]['automated_research_acceptance'])

    def test_independent_index_and_publisher(self):
        x = copy.deepcopy(EVIDENCE)
        e = copy.deepcopy(x['evidence'][0])
        e['source_kind'], e['url'] = 'index', 'https://pubmed.ncbi.nlm.nih.gov/42211174/'
        x['evidence'].append(e)
        self.assertEqual(verify(CANDIDATES, x)['items'][0]['bibliographic_status'], 'publisher_and_index_metadata_match')

    def test_index_only_does_not_claim_publisher(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['source_kind'] = 'index'
        x['evidence'][0]['url'] = 'https://dblp.dagstuhl.de/rec/conf/csai/WangL25a.html'
        self.assertEqual(verify(CANDIDATES, x)['items'][0]['bibliographic_status'], 'index_metadata_match_only')

    def test_wrong_title_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['source_title'] = 'A completely different topic'
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_wrong_doi_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['doi'] = '10.1038/invalid-doi'
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_duplicate_candidates_rejected(self):
        x = copy.deepcopy(CANDIDATES)
        x['items'].append(x['items'][0])
        with self.assertRaises(EvidenceError): verify(x, EVIDENCE)

    def test_missing_evidence_fail_closed(self):
        with self.assertRaises(EvidenceError): verify(CANDIDATES, {'evidence': []})

    def test_http_source_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['url'] = 'http://www.nature.com/articles/s44387-026-00102-5'
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_lookalike_domain_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['url'] = 'https://www.nature.com.evil.invalid/anything'
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_source_type_mismatch_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['source_kind'] = 'index'
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_scientific_claims_attempt_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'][0]['science_reproduced'] = True
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_duplicate_evidence_urls_rejected(self):
        x = copy.deepcopy(EVIDENCE)
        x['evidence'].append(copy.deepcopy(x['evidence'][0]))
        with self.assertRaises(EvidenceError): verify(CANDIDATES, x)

    def test_wrong_issue_rejected(self):
        x = copy.deepcopy(CANDIDATES)
        x['issue_comment_url'] = 'https://github.com/other/repo'
        with self.assertRaises(EvidenceError): verify(x, EVIDENCE)

    def test_cli_and_replay_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'candidate.json').write_text(json.dumps(CANDIDATES))
            (root/'attest.json').write_text(json.dumps(EVIDENCE))
            a, b = root/'a.json', root/'b.json'
            main([str(root/'candidate.json'),str(root/'attest.json'),'--output',str(a)])
            main([str(root/'candidate.json'),str(root/'attest.json'),'--output',str(b)])
            self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_file_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'a.json').write_text('{}')
            (root/'link.json').symlink_to(root/'a.json')
            with self.assertRaises(EvidenceError): read_limited_json(root/'link.json')


if __name__ == '__main__':
    unittest.main()