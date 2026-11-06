"""Bounded retrieval of *actual* Europe PMC research texts for a known DOI.

Only the configured Europe PMC host is contacted, with no user-derived URL.
The returned excerpt demonstrates that text was retrieved; it never certifies
the paper's truth or verifies the model's specific claims.
"""
from __future__ import annotations

import json
from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler


BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest/"
DOI = re.compile(r"^10\.\d{4,9}/[A-Za-z0-9._;()/:+\-]{1,180}$", re.I)
PMC_ID = re.compile(r"^PMC[0-9]{1,14}$")
MAX_BYTES = 1_500_000


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fixed_host_fetch(url):
    """Refuse redirects and limit size; never follow article-supplied links."""
    if not url.startswith(BASE):
        raise ValueError("Unexpected evidence host")
    req = Request(url, headers={"User-Agent": "CANO-Source-Evidence/1.0",
                                "Accept": "application/json, application/xml"})
    with build_opener(_NoRedirect).open(req, timeout=20) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Remote evidence too large")
    return data


def _localname(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _complete_excerpt(text, limit=900):
    excerpt = " ".join(text.split())[:limit]
    if len(excerpt) == limit:
        boundary = max(excerpt.rfind(". "), excerpt.rfind(".\n"))
        if boundary >= limit - 160:
            excerpt = excerpt[:boundary + 1]
    return excerpt


class _StructuredAbstract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self.heading = ""
        self.parts = []
        self.in_heading = False

    def handle_starttag(self, tag, attrs):
        if tag.casefold() in {"h1", "h2", "h3", "h4", "strong", "b"}:
            if self.parts:
                self._flush()
            self.in_heading = True

    def handle_endtag(self, tag):
        if tag.casefold() in {"h1", "h2", "h3", "h4", "strong", "b"}:
            self.heading = " ".join(self.parts).strip()
            self.parts = []
            self.in_heading = False
        elif tag.casefold() in {"p", "div", "br", "li"}:
            self._flush()

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())

    def close(self):
        super().close()
        self._flush()

    def _flush(self):
        text = " ".join(self.parts).strip()
        if text:
            self.sections.append((self.heading, text))
        self.parts = []
        self.heading = ""


def _abstract_excerpt(raw):
    if not isinstance(raw, str) or not raw.strip():
        return ""
    parser = _StructuredAbstract()
    parser.feed(raw[:MAX_BYTES])
    parser.close()
    priorities = ("results", "outcome", "methods", "design", "eligibility",
                  "conclusion", "objective", "background")
    sections = sorted(parser.sections, key=lambda item: next(
        (index for index, word in enumerate(priorities)
         if word in item[0].casefold()), len(priorities)))
    if not sections:
        return " ".join(raw.split())[:900]
    selected = []
    for title, text in sections:
        passage = (title + ": " if title else "") + text
        remaining = 900 - sum(map(len, selected))
        if remaining <= 0:
            break
        selected.append(passage[:remaining])
    return _complete_excerpt(" ".join(selected))


def _xml_excerpt(raw, query=""):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
        raise ValueError("Invalid source document")
    # Reject DTD/entity directives rather than risking XML entity expansion.
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Unsupported XML entity declaration")
    document = ET.fromstring(raw)
    budget = 900
    selected = []

    def clean(node):
        return " ".join("".join(node.itertext()).split())

    abstracts = [el for el in document.iter() if _localname(el.tag) == "abstract"]
    sections = []
    for abstract in abstracts:
        for child in list(abstract):
            name = _localname(child.tag)
            if name not in {"sec", "abstract-sec"}:
                continue
            title = next((clean(node) for node in child.iter()
                          if _localname(node.tag) == "title"), "")
            passage = " ".join(clean(node) for node in child.iter()
                               if _localname(node.tag) in {"p", "label"})
            if not passage:
                passage = clean(child)
            if passage:
                sections.append((title, passage))

    # Prefer the abstract's actual results and methods to the article's opening
    # introduction. The first paragraphs of a long paper rarely answer the task.
    priorities = ("results", "outcome", "methods", "design", "eligibility",
                  "conclusion", "data source", "objective")
    sections.sort(key=lambda item: next(
        (index for index, word in enumerate(priorities)
         if word in item[0].casefold()), len(priorities)))
    if any("result" in title.casefold() for title, _ in sections):
        sections = [(title, passage) for title, passage in sections
                    if any(word in title.casefold() for word in priorities)]
    for title, passage in sections:
        labeled = (title + ": " if title else "") + passage
        if len(labeled) <= budget - sum(map(len, selected)):
            selected.append(labeled)
        elif not selected:
            selected.append(labeled[:budget])
            break
        if sum(map(len, selected)) >= budget:
            break

    # If the abstract is unstructured or short, use query-relevant passages
    # from the article body, including limitations and evidence confidence.
    bodies = [el for el in document.iter() if _localname(el.tag) == "body"]
    query_words = {word.casefold() for word in re.findall(r"[\w-]{4,}", query)}
    aliases = set()
    if query_words.intersection({"walking", "jogging", "yürüyüş", "yuruyus", "koşu", "kosu"}):
        aliases.update(("walking or jogging", "walking/jogging", "running"))
    if query_words.intersection({"certainty", "confidence", "güven", "guven", "bias", "yanlılık", "yanlilik"}):
        aliases.update(("cinema", "low confidence", "very low", "risk of bias", "blinding"))
    body_paragraphs = []
    if bodies:
        for node in bodies[0].iter():
            if _localname(node.tag) != "p":
                continue
            passage = clean(node)
            if not passage:
                continue
            folded = passage.casefold()
            score = sum(1 for word in query_words if word in folded)
            score += 2 * sum(1 for phrase in aliases if phrase in folded)
            if any(word in folded for word in ("results", "sample size", "participants")):
                score += 1
            if score:
                body_paragraphs.append((score, passage))
    body_paragraphs.sort(key=lambda item: item[0], reverse=True)
    if not selected and bodies and not body_paragraphs:
        body_paragraphs = [
            (0, clean(node)) for node in bodies[0].iter()
            if _localname(node.tag) == "p" and clean(node)
        ]
    for _, passage in body_paragraphs:
        if any(passage[:100] in old or old[:100] in passage for old in selected):
            continue
        remaining = budget - sum(map(len, selected))
        if remaining <= 30:
            break
        selected.append(passage[:remaining])

    text = _complete_excerpt(" ".join(selected), budget)
    if not text:
        raise ValueError("No readable article paragraphs")
    return text


def read_publication_evidence(doi, *, fetch=None, query=""):
    """Return a bounded source excerpt with evidence type and non-verified flag."""
    if (not isinstance(doi, str) or doi != doi.strip()
            or not DOI.fullmatch(doi) or ".." in doi or "//" in doi):
        raise ValueError("Invalid DOI")
    doi = doi.lower()
    get = fetch or _fixed_host_fetch
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    canonical = "https://doi.org/" + doi
    base = {"doi": doi, "title": "", "url": canonical, "status": "not_found",
            "excerpt": "", "claim_verified": False, "accessed_at": when}
    search = BASE + "search?" + urlencode({
        "query": "DOI:" + doi, "format": "json", "pageSize": 3,
        "resultType": "core",
    })
    raw = get(search)
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
        raise ValueError("Invalid API response")
    result = json.loads(raw)
    hits = result.get("resultList", {}).get("result", [])
    if not isinstance(hits, list):
        raise ValueError("Unexpected Europe PMC data")
    match = next((item for item in hits
                  if isinstance(item, dict)
                  and isinstance(item.get("doi"), str)
                  and item["doi"].casefold() == doi), None)
    if match is None:
        return base
    title = match.get("title")
    base["title"] = " ".join(title.split())[:200] if isinstance(title, str) else ""
    pmcid = match.get("pmcid")
    if (match.get("isOpenAccess") == "Y" and match.get("inEPMC") == "Y"
            and isinstance(pmcid, str) and PMC_ID.fullmatch(pmcid)):
        url = BASE + pmcid + "/fullTextXML"
        try:
            excerpt = _xml_excerpt(get(url), query=query)
        except (OSError, ValueError, ET.ParseError):
            # The abstract is a separate, weaker form of evidence.
            pass
        else:
            base.update({"url": "https://europepmc.org/articles/" + pmcid,
                         "status": "full_text_excerpt", "excerpt": excerpt})
            return base
    abstract = match.get("abstractText")
    if isinstance(abstract, str) and abstract.strip():
        cleaned = _abstract_excerpt(abstract)
        # Abstract may contain XML markup, and is never treated as full text.
        base.update({"status": "abstract_excerpt", "excerpt": cleaned})
    else:
        base["status"] = "metadata_only"
    return base

