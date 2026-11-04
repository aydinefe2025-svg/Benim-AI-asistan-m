"""Offline bibliographic evidence gate for manually observed publisher/index records.

This module cannot verify scientific claims and does not fetch external URLs.
Independent online observation is recorded separately as provenance. Only DOI
and title agreement may be promoted to a bibliographic match. Fail closed for
bad/missing source attestations, DOI conflicts or unsafe URLs.
"""
import argparse
import datetime as dt
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit

from crossref_discovery import DOI_RE

MAX_RECORDS = 10
MAX_INPUT_BYTES = 128 * 1024
ALLOWED_HOSTS = {
    'ijcseai.com': 'publisher',
    'www.nature.com': 'publisher',
    'www.frontiersin.org': 'publisher',
    'ijcai.org': 'publisher',
    'pubmed.ncbi.nlm.nih.gov': 'index',
    'dblp.dagstuhl.de': 'index',
}
ISSUE_URL = 'https://github.com/aydinefe2025-svg/Benim-AI-asistan-m/issues/164#issuecomment-6632092882'


class EvidenceError(ValueError):
    pass


def normalized_title(title):
    if not isinstance(title, str) or not 5 <= len(title) <= 500:
        raise EvidenceError('invalid title')
    title = unicodedata.normalize('NFKC', title).casefold()
    title = re.sub(r'[^\w]+', ' ', title, flags=re.UNICODE).strip()
    if len(title) < 5:
        raise EvidenceError('empty normalized title')
    return title


def normalized_doi(doi):
    if not isinstance(doi, str) or DOI_RE.fullmatch(doi.strip()) is None:
        raise EvidenceError('invalid DOI')
    return doi.strip().lower()


def validate_source_url(url, kind):
    if kind not in ('publisher', 'index') or not isinstance(url, str) or len(url) > 600:
        raise EvidenceError('source type or URL invalid')
    p = urlsplit(url)
    if p.scheme != 'https' or p.username is not None or p.password is not None or \
            p.port is not None or p.hostname not in ALLOWED_HOSTS or \
            ALLOWED_HOSTS[p.hostname] != kind or not p.path.startswith('/'):
        raise EvidenceError('source is not an allowlisted publisher/index HTTPS URL')
    return url


def verify(candidates, attestations):
    if not isinstance(candidates, dict) or candidates.get('issue_comment_url') != ISSUE_URL or \
       not isinstance(candidates.get('items'), list) or not 1 <= len(candidates['items']) <= MAX_RECORDS:
        raise EvidenceError('untrusted candidate envelope')
    if not isinstance(attestations, dict) or not isinstance(attestations.get('evidence'), list):
        raise EvidenceError('untrusted evidence envelope')
    expected = {}
    for x in candidates['items']:
        if not isinstance(x, dict):
            raise EvidenceError('bad candidate')
        d = normalized_doi(x.get('doi'))
        title = normalized_title(x.get('title'))
        if d in expected:
            raise EvidenceError('duplicate candidate DOI')
        expected[d] = (x['title'], title)
    matches = {d: [] for d in expected}
    seen_urls = set()
    for x in attestations['evidence']:
        if not isinstance(x, dict) or x.get('observation_method') != 'web_source_inspection':
            raise EvidenceError('invalid evidence or observation method')
        d = normalized_doi(x.get('doi'))
        if d not in expected:
            raise EvidenceError('unrelated DOI injected into evidence')
        if normalized_title(x.get('source_title')) != expected[d][1]:
            raise EvidenceError('DOI/title mismatch for ' + d)
        u = validate_source_url(x.get('url'), x.get('source_kind'))
        if u in seen_urls:
            raise EvidenceError('reused evidence URL')
        seen_urls.add(u)
        if x.get('science_reproduced') is not False:
            raise EvidenceError('scientific replication cannot be asserted from bibliography')
        matches[d].append({'url': u, 'source_kind': x['source_kind']})
    out = []
    for doi, (title, _) in expected.items():
        ev = matches[doi]
        if not ev:
            raise EvidenceError('missing independent bibliographic source for ' + doi)
        pub = any(x['source_kind'] == 'publisher' for x in ev)
        idx = any(x['source_kind'] == 'index' for x in ev)
        # Primary page confirms only bibliographic identity, not quality or results.
        status = ('publisher_and_index_metadata_match' if pub and idx else
                  'publisher_metadata_match' if pub else 'index_metadata_match_only')
        out.append({'doi': doi, 'title': title, 'bibliographic_status': status,
                    'scientific_claims_verified': False,
                    'automated_research_acceptance': False,
                    'follow_up': 'independent methods/data review required',
                    'source_evidence': ev})
    return {'schema_version': 1, 'issue_comment_url': ISSUE_URL,
            'record_count': len(out), 'bibliographic_matches': len(out),
            'scientific_claims_verified': 0,
            'review_status': 'bibliographic_screen_only', 'items': out}


def read_limited_json(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_INPUT_BYTES:
        raise EvidenceError('input missing or unsafe')
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError('invalid JSON') from exc


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('candidates')
    parser.add_argument('attestations')
    parser.add_argument('--output', default='doi_evidence_screen.json')
    args = parser.parse_args(argv)
    report = verify(read_limited_json(args.candidates), read_limited_json(args.attestations))
    target = Path(args.output)
    if target.is_symlink() or not target.parent.is_dir():
        raise EvidenceError('unsafe destination')
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('record_count', 'bibliographic_matches', 'scientific_claims_verified')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())