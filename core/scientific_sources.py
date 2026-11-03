"""Bounded Crossref discovery. Publisher metadata is a lead, never claim proof.

API contract: https://github.com/Crossref/rest-api-doc
No page URLs from responses are fetched; only the fixed Crossref API is used.
"""
from datetime import datetime, timezone
import json
import math
import re
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from core.retry_policy import retry_transient

MAX_RESPONSE_BYTES = 1_000_000
DOI = re.compile(r'10\.\d{4,9}/[^\s<>"#?]+', re.IGNORECASE)


def _fetch(url):
    with urlopen(Request(url, headers={'User-Agent': 'ResearchAssistant/1.0',
                                      'Accept': 'application/json'}), timeout=8) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError('Metadata response exceeds limit')
        return json.loads(raw)


def scientific_sources(query, limit=3, fetch=None):
    if not isinstance(query, str) or not query.strip():
        return []
    limit = max(1, min(int(limit), 5))
    url = 'https://api.crossref.org/works?' + urlencode({
        'query.bibliographic': query.strip()[:200], 'rows': limit,
        'sort': 'relevance', 'order': 'desc',
    })
    data = retry_transient(lambda: (fetch or _fetch)(url))
    if not isinstance(data, dict) or not isinstance(data.get('message'), dict):
        raise ValueError('Invalid metadata response')
    items = data['message'].get('items')
    if not isinstance(items, list):
        raise ValueError('Invalid work collection')
    result, seen = [], set()
    accessed = datetime.now(timezone.utc).isoformat(timespec='seconds')
    for work in items[:10]:
        if not isinstance(work, dict):
            continue
        doi, titles = work.get('DOI'), work.get('title')
        if (not isinstance(doi, str) or DOI.fullmatch(doi) is None or
                not isinstance(titles, list) or not titles or
                not isinstance(titles[0], str) or not titles[0].strip()):
            continue
        doi = doi.lower()
        if doi in seen:
            continue
        seen.add(doi)
        published = ''
        dates = work.get('published', {})
        parts = dates.get('date-parts', []) if isinstance(dates, dict) else []
        if parts and isinstance(parts[0], list):
            date = parts[0]
            if 1 <= len(date) <= 3 and all(type(x) is int for x in date):
                try:
                    datetime(*(date + [1] * (3 - len(date))))
                    published = '-'.join(str(x) if i == 0 else f'{x:02}' for i, x in enumerate(date))
                except ValueError:
                    pass
        score = work.get('score')
        score = score if type(score) in (int, float) and math.isfinite(score) else None
        publisher = work.get('publisher')
        result.append({'title': titles[0].strip()[:300],
                       'url': 'https://doi.org/' + quote(doi, safe='/():;._-'),
                       'doi': doi, 'publisher': publisher[:200] if isinstance(publisher, str) else '',
                       'published_at': published, 'accessed_at': accessed,
                       'relevance_score': score, 'confidence': 'unassessed',
                       'stage': 'source_lead', 'retrieval': 'publisher_metadata',
                       'primary_source_review': 'required', 'verified': False})
    # Preserve provider relevance order; title alphabetization loses relevance.
    return result[:limit]
