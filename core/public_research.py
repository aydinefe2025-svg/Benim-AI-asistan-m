"""Bounded public source lookup, returning auditable URLs."""
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

API = "https://en.wikipedia.org/w/api.php"


def research_sources(query, limit=3, fetch=None):
    if not isinstance(query, str) or not query.strip():
        return []
    limit = max(1, min(int(limit), 5))
    params = {"action": "query", "generator": "search", "gsrsearch": query.strip()[:200], "gsrlimit": limit, "prop": "info", "inprop": "url", "format": "json"}
    url = API + "?" + urlencode(params)
    if fetch is None:
        def fetch(url):
            with urlopen(Request(url, headers={"User-Agent": "ResearchAssistant/1.0"}), timeout=6) as response:
                return json.load(response)
    pages = fetch(url).get("query", {}).get("pages", {})
    results = []
    ranked_pages = sorted(pages.values(), key=lambda page: page.get("index", 999999))
    seen = set()
    for page in ranked_pages:
        title, source = page.get("title"), page.get("fullurl")
        if isinstance(title, str) and isinstance(source, str) and source.startswith("https://en.wikipedia.org/wiki/"):
            if source not in seen:
                seen.add(source)
                results.append({"title": title[:200], "url": source})
    return results[:limit]
