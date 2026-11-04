"""One-request, allowlisted Crossref metadata discovery; metadata is NOT scientific validation.

No user-supplied URLs, no redirects, bounded response, no paper abstracts/full text.
Default output is only a pending-review JSON document.
"""
import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = 'https://api.crossref.org/works'
TOPICS = {
    'robotics': 'bio inspired robotics soft actuators',
    'materials': 'biomimetic functional materials',
    'biology': 'cellular mechanics quantitative modeling',
    'history': 'history of engineering ancient technology',
    'artificial_intelligence': 'scientific discovery multi agent artificial intelligence',
}
MAX_RESPONSE_BYTES = 512 * 1024
MAX_RECORDS = 5
DOI_RE = re.compile(r'^10\.[0-9]{4,9}/[^\s<>"\']{1,180}$', re.I)
CTRL_RE = re.compile(r'[\x00-\x1f\x7f]')
# Crossref's bibliographic search also matches author/journal metadata. Reject titles
# without explicit topic anchors instead of filling the review queue with unrelated DOIs.
TOPIC_TITLE_SIGNALS = {
    'robotics': re.compile(r'\b(robot(?:ic|ics|s)?|biorobotic|bio-inspired|actuator|locomotion|biomimetic)\b', re.I),
    'materials': re.compile(r'\b(materials?|biomimetic|hydrogels?|metamaterials?|nanostructures?|polymers?|composites?)\b', re.I),
    'biology': re.compile(r'\b(cells?|cellular|tissues?|mechanobiology|biomechanics|morphogenesis|cardiomyocytes?)\b', re.I),
    'history': re.compile(r'\b(ancient|medieval|archaeolog(?:y|ical)|history|historical|antiquity|industrial revolution)\b', re.I),
    'artificial_intelligence': re.compile(r'\b(artificial intelligence|machine learning|deep learning|large language models?|multi[- ]agents?|agentic|autonomous agents?|neural networks?|language models?|foundation models?|AI[- ]driven|scientific discovery)\b', re.I),
}


class FeedError(RuntimeError):
    pass


class DenyRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise FeedError('Crossref redirect denied')


def choose_topic(when=None):
    today = (when or dt.datetime.now(dt.timezone.utc)).date()
    return list(TOPICS)[today.toordinal() % len(TOPICS)]


def build_url(topic, rows=MAX_RECORDS):
    if topic not in TOPICS or type(rows) is not int or not 1 <= rows <= MAX_RECORDS:
        raise ValueError('topic/row limit not allowed')
    query = urllib.parse.urlencode({
        'query.bibliographic': TOPICS[topic], 'rows': rows,
        'select': 'DOI,title,type,published,container-title,URL',
        'filter': 'from-pub-date:2024-01-01,until-pub-date:' + dt.datetime.now(dt.timezone.utc).date().isoformat(),
        'sort': 'relevance', 'order': 'desc',
    })
    return API + '?' + query


def clean_title(raw):
    if not isinstance(raw, str):
        return ''
    clean = html.unescape(re.sub(r'<[^>]{0,1024}>', ' ', raw))
    clean = CTRL_RE.sub(' ', clean).replace('`', "'").replace('[', '(').replace(']', ')')
    return ' '.join(clean.split())[:260]


def paper_date(item):
    if not isinstance(item, dict):
        return None
    parts = item.get('date-parts')
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list):
        return None
    try:
        ys = parts[0]
        year = int(ys[0])
        month = int(ys[1]) if len(ys) > 1 else 1
        day = int(ys[2]) if len(ys) > 2 else 1
        return dt.date(year, month, day).isoformat()
    except (TypeError, IndexError, ValueError, OverflowError):
        return None


def parse_crossref_response(payload, topic, fetched_at=None):
    if topic not in TOPICS or not isinstance(payload, dict) or payload.get('status') != 'ok':
        raise FeedError('Crossref response status invalid')
    message = payload.get('message')
    if not isinstance(message, dict) or not isinstance(message.get('items'), list):
        raise FeedError('Crossref response has no items')
    if len(message['items']) > MAX_RECORDS:
        raise FeedError('Crossref response exceeded row limit')
    entries, seen = [], set()
    for item in message['items']:
        if not isinstance(item, dict):
            continue
        doi = item.get('DOI')
        title = item.get('title')
        if not isinstance(doi, str) or DOI_RE.fullmatch(doi.strip()) is None:
            continue
        doi = doi.strip().lower()
        if isinstance(title, list):
            title = title[0] if title else ''
        title = clean_title(title)
        if not title or doi in seen or TOPIC_TITLE_SIGNALS[topic].search(title) is None:
            continue
        seen.add(doi)
        entries.append({
            'doi': doi,
            'title': title,
            'url': 'https://doi.org/' + urllib.parse.quote(doi, safe='/.-_()'),
            'published': paper_date(item.get('published')),
            'type': clean_title(item.get('type', ''))[:60],
            'source': 'Crossref public REST API',
            'review_status': 'pending_review',
        })
    if not entries:
        raise FeedError('No topic-relevant DOI metadata in Crossref response')
    return {'schema_version': 1, 'topic': topic,
            'fetched_at': fetched_at or dt.datetime.now(dt.timezone.utc).isoformat(),
            'source_api': API, 'items': entries, 'relevance_policy': 'topic_title_anchor',
            'claims_verified': False, 'content_downloaded': False}


def fetch_crossref(topic, rows=MAX_RECORDS, opener=None):
    url = build_url(topic, rows)
    op = opener or urllib.request.build_opener(DenyRedirect())
    req = urllib.request.Request(url, headers={
        'User-Agent': 'CANO-Research-Metadata/1.0 (noncommercial bounded metadata review)',
        'Accept': 'application/json',
    })
    try:
        with op.open(req, timeout=15) as response:
            if response.status != 200:
                raise FeedError('Crossref returned HTTP ' + str(response.status))
            if response.geturl() != url:
                raise FeedError('Crossref redirected unexpectedly')
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise FeedError('Crossref rate limited: retry on next scheduled run') from exc
        raise FeedError('Crossref HTTP ' + str(exc.code)) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FeedError('Crossref network error: ' + str(exc)[:160]) from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise FeedError('Crossref response too large')
    try:
        parsed = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FeedError('Crossref response is not JSON') from exc
    return parse_crossref_response(parsed, topic)


def save_json(data, path):
    target = Path(path)
    if target.is_symlink() or not target.parent.is_dir():
        raise FeedError('unsafe output path')
    # Never write a partial file over the last successful output.
    tmp = target.with_name(target.name + '.tmp')
    try:
        with tmp.open('x', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv=None):
    p = argparse.ArgumentParser(description='Bounded Crossref DOI metadata poll')
    p.add_argument('--topic', choices=['auto', *TOPICS], default='auto')
    p.add_argument('--rows', type=int, default=MAX_RECORDS)
    p.add_argument('--output', default='crossref_pending_review.json')
    args = p.parse_args(argv)
    topic = choose_topic() if args.topic == 'auto' else args.topic
    try:
        value = fetch_crossref(topic, args.rows)
        save_json(value, args.output)
        print(json.dumps({'ok': True, 'topic': topic, 'count': len(value['items']),
                          'pending_review': len(value['items'])}))
        return 0
    except (FeedError, ValueError, FileExistsError, OSError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)[:230]}), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
