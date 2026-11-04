"""Persist Crossref *unverified* DOI metadata into one designated GitHub issue.

Fail-closed if the issue's entire bounded history cannot be inspected. No issue
creation, no branch changes, no arbitrary URL inputs, one comment per invocation.
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from crossref_discovery import DOI_RE, DenyRedirect

MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PAGES = 10
REPO_PATTERN = re.compile(r'^[A-Za-z0-9_.-]{1,90}/[A-Za-z0-9_.-]{1,90}$')
MARKER = re.compile(r'<!-- CANO-DOI:([^\s<>]+) -->')


class PublishError(RuntimeError):
    pass


def read_json(path):
    p = Path(path)
    if p.is_symlink() or not p.is_file() or p.stat().st_size > MAX_RESPONSE_BYTES:
        raise PublishError('unsafe pending JSON')
    with p.open('r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict) or data.get('claims_verified') is not False or \
       data.get('content_downloaded') is not False or not isinstance(data.get('items'), list) \
       or not 1 <= len(data['items']) <= 5:
        raise PublishError('metadata envelope invalid')
    return data


def validate_issues_config(repository, issue, token):
    if not isinstance(repository, str) or not REPO_PATTERN.fullmatch(repository) or \
       repository.startswith('.') or '/.' in repository or \
       not isinstance(issue, int) or not 1 <= issue <= 2147483647 or \
       not isinstance(token, str) or len(token.strip()) < 8:
        raise PublishError('GitHub auth or issue configuration invalid')
    return f'https://api.github.com/repos/{repository}/issues/{issue}/comments'


def request_json(url, token, method='GET', data=None, opener=None):
    # URLs always built by validate_issues_config plus a constant page query.
    if not url.startswith('https://api.github.com/repos/'):
        raise PublishError('untrusted URL')
    raw = None if data is None else json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(url, data=raw, method=method, headers={
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'CANO-Research-Metadata/1.0',
        'Authorization': 'Bearer ' + token,
        'X-GitHub-Api-Version': '2022-11-28',
        **({'Content-Type': 'application/json'} if raw is not None else {}),
    })
    op = opener or urllib.request.build_opener(DenyRedirect())
    try:
        with op.open(req, timeout=15) as response:
            if response.status not in ({200, 201} if method == 'POST' else {200}):
                raise PublishError('GitHub rejected request')
            if response.geturl() != url:
                raise PublishError('redirect denied')
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise PublishError('GitHub HTTP ' + str(exc.code)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PublishError('GitHub connection failed: ' + str(exc)[:100]) from exc
    if len(body) > MAX_RESPONSE_BYTES:
        raise PublishError('GitHub response too large')
    try:
        return json.loads(body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PublishError('GitHub response invalid JSON') from exc


def read_seen_markers(url, token, request=request_json):
    seen = set()
    for page in range(1, MAX_PAGES + 1):
        comments = request(f'{url}?per_page=100&page={page}', token)
        if not isinstance(comments, list):
            raise PublishError('GitHub issue comments not a list')
        for c in comments:
            if not isinstance(c, dict) or not isinstance(c.get('body'), str):
                raise PublishError('invalid issue comment')
            seen.update(d.lower() for d in MARKER.findall(c['body']))
        if len(comments) < 100:
            return seen
    raise PublishError('GitHub issue history too large: cannot guarantee deduplication')


def markdown_preview(data, seen):
    new, used = [], set()
    for item in data['items']:
        if not isinstance(item, dict):
            raise PublishError('invalid paper item')
        doi = item.get('doi')
        title, url = item.get('title'), item.get('url')
        if not isinstance(doi, str) or not DOI_RE.fullmatch(doi) or \
           not isinstance(title, str) or not 1 <= len(title) <= 260 or \
           not isinstance(url, str) or not url.startswith('https://doi.org/'):
            raise PublishError('invalid DOI metadata')
        if doi.lower() in seen or doi.lower() in used:
            continue
        used.add(doi.lower())
        new.append((doi, title, url))
    if not new:
        return '', 0
    # DOI links are reconstructed from validated identifiers, never from input URLs.
    from urllib.parse import quote
    lines = ['### CANO günlük DOI inceleme kuyruğu (otomatik meta-veri)',
             'Kaynak: Crossref. **Bilimsel iddialar doğrulanmadı; özet/tam metin okunmadı.**',
             f"Konu: {data.get('topic', 'unknown')} | Durum: `pending_review`", '']
    for doi, title, _ in new:
        clean_title = title.replace('\n', ' ').replace('\r', ' ').replace('`', "'")
        clean_title = re.sub(r'[<>\[\]\\]', '', clean_title)[:260]
        link = 'https://doi.org/' + quote(doi, safe='/')
        lines += [f'- **{clean_title}** — <{link}>', f'  <!-- CANO-DOI:{doi.lower()} -->']
    body = '\n'.join(lines)
    if len(body.encode('utf-8')) > 15000:
        raise PublishError('GitHub comment too long')
    return body, len(new)


def publish(data, repository, issue, token, request=request_json):
    url = validate_issues_config(repository, issue, token)
    seen = read_seen_markers(url, token, request=request)
    body, count = markdown_preview(data, seen)
    if not count:
        return {'ok': True, 'posted': 0, 'skipped': len(data['items']), 'reason': 'all DOIs already present'}
    result = request(url, token, method='POST', data={'body': body})
    if not isinstance(result, dict) or not isinstance(result.get('id'), int) or \
       not isinstance(result.get('html_url'), str):
        raise PublishError('GitHub comment receipt invalid')
    # Explicit readback: do not report persisted without seeing our markers.
    confirmed = read_seen_markers(url, token, request=request)
    if not all(item['doi'].lower() in confirmed for item in data['items'] if item['doi'].lower() not in seen):
        raise PublishError('GitHub comment not visible on readback')
    return {'ok': True, 'posted': count, 'skipped': len(data['items']) - count,
            'comment_url': result['html_url']}


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument('metadata', type=Path)
    args = p.parse_args(argv)
    try:
        data = read_json(args.metadata)
        repo = os.environ.get('GITHUB_REPOSITORY', '')
        issue = int(os.environ.get('CANO_REVIEW_ISSUE', '0'))
        token = os.environ.get('GITHUB_TOKEN', '')
        result = publish(data, repo, issue, token)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (PublishError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)[:200]}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
