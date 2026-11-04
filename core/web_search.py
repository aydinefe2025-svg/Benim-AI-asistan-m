"""Small public-web search adapter; results are snippets, not verified sources."""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlparse
from urllib.request import Request, urlopen


class SearchError(RuntimeError):
    """Raised when web search cannot be completed."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    publisher: str


class _DuckDuckGoParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self.current: dict[str, str] | None = None
        self.capture: str | None = None
        self.buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = (attributes.get("class") or "").split()
        if tag == "div" and any(c == "result" for c in classes) and self.current is None:
            self.current = {"title": "", "url": "", "snippet": ""}
        if self.current is None:
            return
        if tag == "a" and "result__a" in classes:
            self.current["url"] = attributes.get("href") or ""
            self.capture = "title"
            self.buffer = []
        elif tag in {"a", "div"} and "result__snippet" in classes:
            self.capture = "snippet"
            self.buffer = []

    def handle_data(self, data: str) -> None:
        if self.capture:
            self.buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.capture and ((self.capture == "title" and tag == "a") or (self.capture == "snippet" and tag in {"a", "div"})):
            if self.current is not None:
                self.current[self.capture] += "".join(self.buffer).strip()
            self.capture = None
            self.buffer = []
        if tag == "div" and self.current is not None:
            if self.current.get("title") and self.current.get("url"):
                self.results.append(self.current)
                self.current = None


def _unwrap_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url if "://" in url else "https:" + url if url.startswith("//") else url)
    if parsed.hostname and parsed.hostname.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            url = unquote(target)
    return url


class DuckDuckGoSearch:
    """Search DuckDuckGo HTML and return result snippets without fetching source pages."""

    def __init__(self, timeout: int = 12) -> None:
        self.timeout = timeout

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        if max_results < 1:
            raise ValueError("max_results must be at least 1")
        request = Request(
            "https://html.duckduckgo.com/html/?q=" + quote_plus(query),
            headers={"User-Agent": "Mozilla/5.0 (compatible; ResearchAssistant/1.0)"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                html = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            raise SearchError(f"DuckDuckGo returned HTTP {exc.code}") from exc
        except (URLError, TimeoutError) as exc:
            raise SearchError(f"DuckDuckGo request failed: {exc}") from exc

        parser = _DuckDuckGoParser()
        parser.feed(html)
        output: list[SearchResult] = []
        seen: set[str] = set()
        for item in parser.results:
            url = _unwrap_url(item.get("url", ""))
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen:
                continue
            seen.add(url)
            output.append(SearchResult(
                title=" ".join(item.get("title", "").split()),
                url=url,
                snippet=" ".join(item.get("snippet", "").split()),
                publisher=parsed.hostname or "",
            ))
            if len(output) >= max_results:
                break
        if not output:
            raise SearchError("No search results parsed; request may be blocked or page structure changed")
        return output
