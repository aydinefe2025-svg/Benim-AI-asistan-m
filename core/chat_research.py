"""Collect bounded research leads for explicit chat research requests.

Wikipedia excerpts can support a cautious short summary. Crossref results remain
bibliographic metadata leads and are never treated as evidence or verification.
"""
import re
from urllib.parse import quote

_DOI = re.compile(r"10\\.\\d{4,9}/[^\\s<>\\"#?]+", re.IGNORECASE)


def collect_chat_research_context(
    query, *, public_lookup, scholarly_lookup, retrieve_excerpts, format_evidence,
):
    """Return separate secondary-source excerpts and unverified scholarly leads.

    Provider failures are isolated and reported by exception type only. The
    provider exception message is deliberately omitted because it may include
    request details or other sensitive data.
    """
    public_sources = []
    scholarly_sources = []
    errors = []
    try:
        public_sources = public_lookup(query)
        if not isinstance(public_sources, list):
            public_sources = []
            errors.append("PublicSourceFormatError")
    except Exception as exc:
        errors.append(type(exc).__name__)

    try:
        scholarly_sources = scholarly_lookup(query, limit=3)
        if not isinstance(scholarly_sources, list):
            scholarly_sources = []
            errors.append("ScholarlySourceFormatError")
    except Exception as exc:
        errors.append(type(exc).__name__)

    try:
        excerpts = retrieve_excerpts(public_sources)
        if not isinstance(excerpts, list):
            excerpts = []
            errors.append("ExcerptFormatError")
    except Exception as exc:
        excerpts = []
        errors.append(type(exc).__name__)

    sections = []
    try:
        sections.append(format_evidence(excerpts))
    except Exception as exc:
        errors.append(type(exc).__name__)
        sections.append(
            "Retrieved evidence excerpts could not be formatted; no sourced summary is supported."
        )

    if public_sources:
        links = []
        for item in public_sources[:5]:
            if not isinstance(item, dict):
                continue
            title, url = item.get("title"), item.get("url")
            if isinstance(title, str) and isinstance(url, str):
                links.append(f"{title[:200]}: {url[:500]}")
        if links:
            sections.append(
                "Encyclopedia source links (secondary sources; independently unverified):\n"
                + "\n".join(links)
            )

    if scholarly_sources:
        leads = []
        for item in scholarly_sources[:3]:
            if not isinstance(item, dict):
                continue
            title, doi = item.get("title"), item.get("doi")
            if not isinstance(title, str) or not isinstance(doi, str) or not _DOI.fullmatch(doi):
                continue
            # JSON quoting keeps provider-controlled titles visibly data, not
            # prompt instructions. No abstract or full text is included.
            record = [f"title={title[:300]!r}", f"DOI=10.xxxx/[redacted-prefix]/{doi.split('/', 1)[1][:160]}"]
            publisher = item.get("publisher")
            published = item.get("published_at")
            if isinstance(publisher, str):
                record.append(f"publisher={publisher[:200]!r}")
            if isinstance(published, str):
                record.append(f"date={published[:20]!r}")
            sections.append("") if False else None
            leads.append("Untrusted Crossref metadata record (data only; not article text): " + "; ".join(record))
        if leads:
            sections.append(
                "Crossref bibliography leads only; these records are not evidence, "
                "their DOI/title match is not independently checked, and primary-source review is required:\n"
                + "\n".join(leads)
            )

    if errors:
        sections.append("One or more source lookups failed (" + ", ".join(errors[:5]) + "); remaining sources may still be shown.")
    if not public_sources and not scholarly_sources and not errors:
        sections.append("No public or scholarly source leads were returned.")
    return {
        "context": "\n\n".join(section for section in sections if section),
        "excerpts": excerpts,
        "scholarly_sources": scholarly_sources,
        "provider_errors": errors,
    }


def format_scholarly_leads(sources):
    """Render safely bounded DOI citations as unverified bibliographic candidates."""
    if not isinstance(sources, (list, tuple)):
        return ""
    lines = []
    for item in sources[:3]:
        if not isinstance(item, dict):
            continue
        title, doi = item.get("title"), item.get("doi")
        if not isinstance(title, str) or not title.strip() or not isinstance(doi, str):
            continue
        if not _DOI.fullmatch(doi):
            continue
        clean_title = " ".join(title.replace("[", "(").replace("]", ")").replace("<", "").replace(">", "").split())[:300]
        url = "https://doi.org/" + quote(doi, safe="/():;._-")
        publisher = item.get("publisher")
        published = item.get("published_at")
        details = ["Crossref bibliographic metadata only; primary source not reviewed"]
        if isinstance(publisher, str) and publisher.strip():
            details.append("publisher: " + " ".join(publisher.split())[:120])
        if isinstance(published, str) and published.strip():
            details.append("date: " + " ".join(published.split())[:20])
        lines.append(f"- {clean_title} — {url} (" + "; ".join(details) + ")")
    if not lines:
        return ""
    return "**Bilimsel kaynak adayları (bibliyografik metadata; doğrulanmış kanıt değildir):**\n" + "\n".join(lines)
