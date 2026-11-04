"""Bounded retrieval of *actual* Europe PMC research texts for a known DOI.

Only the configured Europe PMC host is contacted, with no user-derived URL.
The returned excerpt demonstrates that text was retrieved; it never certifies
the paper's truth or verifies the model's specific claims.
"""
from __future__ import annotations

import json
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
    with build_opener(_NoRedirect).open(req, timeout=8) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("Remote evidence too large")
    return data


def _localname(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _xml_excerpt(raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BYTES:
        raise ValueError("Invalid source document")
    # Reject DTD/entity directives rather than risking XML entity expansion.
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("Unsupported XML entity declaration")
    document = ET.fromstring(raw)
    bodies = [el for el in document.iter() if _localname(el.tag) == "body"]
    if not bodies:
        raise ValueError("No readable article body")
    excerpts = []
    for node in bodies[0].iter():
        if _localname(node.tag) == "p":
            passage = " ".join("".join(node.itertext()).split())
            if passage:
                excerpts.append(passage[:400])
        if len(excerpts) >= 5:
            break
    text = " ".join(excerpts)[:900]
    if not text:
        raise ValueError("No readable article paragraphs")
    return text


def read_publication_evidence(doi, *, fetch=None):
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
            excerpt = _xml_excerpt(get(url))
        except (OSError, ValueError, ET.ParseError):
            # The abstract is a separate, weaker form of evidence.
            pass
        else:
            base.update({"url": "https://europepmc.org/articles/" + pmcid,
                         "status": "full_text_excerpt", "excerpt": excerpt})
            return base
    abstract = match.get("abstractText")
    if isinstance(abstract, str) and abstract.strip():
        cleaned = " ".join(abstract.split())[:900]
        # Abstract may contain XML markup, and is never treated as full text.
        base.update({"status": "abstract_excerpt", "excerpt": cleaned})
    else:
        base["status"] = "metadata_only"
    return base
