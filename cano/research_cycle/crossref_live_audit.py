"""Independently cross-check human-reviewed DOI/title pairs with Crossref REST.

This checks publisher-deposited bibliographic metadata ONLY. It does not verify
scientific conclusions, peer review, full text or claimed experiment results.
Only https://api.crossref.org/works/{DOI} is contacted, sequentially and capped.
"""
import argparse
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from doi_evidence_gate import ISSUE_URL, EvidenceError, normalized_doi, normalized_title
from crossref_discovery import DenyRedirect, FeedError, clean_title

CROSSREF = 'https://api.crossref.org/works/'
MAX_ITEMS = 5
MAX_INPUT_BYTES = 16 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
DEFAULT_SLEEP = 0.3  # public REST pool: stay comfortably below request limit


class AuditError(Exception):
    pass


def parse_candidates(payload):
    if not isinstance(payload, dict) or payload.get('issue_comment_url') != ISSUE_URL:
        raise AuditError('unexpected candidate source')
    items = payload.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise AuditError('invalid candidate count')
    result, seen = [], set()
    try:
        for x in items:
            if not isinstance(x, dict):
                raise AuditError('invalid candidate record')
            doi = normalized_doi(x.get('doi'))
            title = x.get('title')
            canonical = normalized_title(title)
            if doi in seen:
                raise AuditError('duplicate candidate DOI')
            seen.add(doi)
            result.append({'doi': doi, 'title': title, 'canonical_title': canonical})
    except EvidenceError as e:
        raise AuditError(str(e)) from e
    return result


def _open_json(doi, opener=None):
    # DOI is strictly validated by parse_candidates(); encoded slash keeps
    # caller-controlled DOI bytes inside the fixed Crossref path.
    url = CROSSREF + urllib.parse.quote(doi, safe='')
    req = urllib.request.Request(url, headers={
        'User-Agent': 'CANO-DOI-Evidence-Audit/1.0 (noncommercial bounded lookup)',
        'Accept': 'application/json',
    })
    op = opener or urllib.request.build_opener(DenyRedirect())
    try:
        with op.open(req, timeout=12) as res:
            if res.geturl() != url:
                raise AuditError('redirected DOI lookup')
            if res.status != 200:
                raise AuditError('Crossref lookup HTTP ' + str(res.status))
            if 'application/json' not in res.headers.get('Content-Type', '').lower():
                raise AuditError('Crossref response is not JSON content type')
            raw = res.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 429:
            raise AuditError('Crossref rate limit; retry in a later run') from e
        raise AuditError('Crossref HTTP failure ' + str(e.code)) from e
    except FeedError as e:
        raise AuditError('Crossref redirect blocked') from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AuditError('Crossref lookup failed: ' + type(e).__name__) from e
    if len(raw) > MAX_RESPONSE_BYTES:
        raise AuditError('Crossref response too large')
    try:
        doc = json.loads(raw.decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as e:
        raise AuditError('Crossref invalid JSON') from e
    if not isinstance(doc, dict) or doc.get('status') != 'ok' or not isinstance(doc.get('message'), dict):
        raise AuditError('Crossref invalid envelope')
    return doc['message']


def audit(payload, opener=None, sleeper=time.sleep, checked_at=None):
    entries = parse_candidates(payload)
    checked = []
    for i, item in enumerate(entries):
        if i:
            sleeper(DEFAULT_SLEEP)
        metadata = _open_json(item['doi'], opener=opener)
        status, crossref_title, doc_type = 'not_found_in_crossref', None, None
        if metadata is not None:
            crossref_doi = metadata.get('DOI')
            try:
                crossref_doi = normalized_doi(crossref_doi)
            except EvidenceError:
                raise AuditError('Crossref returned invalid DOI')
            if crossref_doi != item['doi']:
                raise AuditError('Crossref returned a different DOI')
            raw_titles = metadata.get('title')
            crossref_title = clean_title(raw_titles[0]) if isinstance(raw_titles, list) and raw_titles else ''
            doc_type = clean_title(metadata.get('type', ''))[:60]
            if not crossref_title:
                status = 'crossref_title_missing'
            else:
                try:
                    status = ('crossref_doi_title_match' if
                              normalized_title(crossref_title) == item['canonical_title'] else
                              'crossref_title_disagrees')
                except EvidenceError:
                    status = 'crossref_title_invalid'
        checked.append({
            'doi': item['doi'], 'candidate_title': item['title'],
            'crossref_title': crossref_title,
            'crossref_type': doc_type,
            'crossref_status': status,
            'science_reproduced': False,
            'automated_acceptance': False,
        })
    return {
        'schema_version': 1,
        'source': 'Crossref REST /works/{doi} — publisher-deposited metadata',
        'candidate_issue_url': ISSUE_URL,
        'checked_at_utc': checked_at or dt.datetime.now(dt.timezone.utc).isoformat(),
        'records_checked': len(checked),
        'crossref_doi_title_matches': sum(x['crossref_status'] == 'crossref_doi_title_match' for x in checked),
        'scientific_claims_reproduced': 0,
        'items': checked,
    }


def read_candidates(path):
    path = Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_INPUT_BYTES:
        raise AuditError('candidate file missing/unsafe/too big')
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise AuditError('bad candidate JSON') from exc


def write_atomic(report, path):
    p = Path(path)
    if not p.parent.is_dir() or p.is_symlink():
        raise AuditError('unsafe output path')
    tmp = p.with_name(p.name + '.tmp')
    if tmp.is_symlink():
        raise AuditError('unsafe temporary path')
    data = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    created = False
    try:
        with tmp.open('x', encoding='utf-8') as f:
            created = True
            f.write(data)
            f.flush()
        tmp.replace(p)
    finally:
        if created:
            tmp.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Crossref independent bibliographic metadata audit (not science validation)')
    parser.add_argument('candidates')
    parser.add_argument('--output', default='crossref_live_review.json')
    args = parser.parse_args(argv)
    try:
        report = audit(read_candidates(args.candidates))
        write_atomic(report, args.output)
    except (AuditError, OSError, ValueError) as e:
        parser.exit(2, f'Crossref audit failed safely: {e}\n')
    print(json.dumps({'checked': report['records_checked'],
                      'crossref_doi_title_matches': report['crossref_doi_title_matches'],
                      'scientific_claims_reproduced': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
