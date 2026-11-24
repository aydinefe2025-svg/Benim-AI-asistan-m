"""Read-only owner-scoped work inventory for explicit Turkish overview questions."""
import re
import unicodedata
from collections.abc import Mapping


def _normalized(value):
    value = unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
    return " ".join(re.findall(r"[a-z0-9]+", "".join(
        c for c in value if not unicodedata.combining(c))))


def _literal(value, limit):
    value = " ".join(str(value or "").split())[:limit]
    return re.sub(r'([\\\x60*_{}\[\]()<>#+.!|~-])', r'\\\1', value)


def work_inventory_reply(query, *, authenticated, memory_loader=None,
                         research_loader=None, queue_loader=None, code_loader=None):
    """No model calls, cross-owner lookups, changes, or external archive guesses.

    Loaders must already be bound to the current authenticated owner's stores.
    Missing/unreadable data is never silently interpreted as an empty library.
    """
    if not isinstance(query, str):
        return None
    prompt = _normalized(query)
    if not re.fullmatch(
        r"(?:cano )?(?:(?:hafizandaki |hafizadaki |kayitli )?"
        r"calismalarimiz (?:nelerdir|neler|ne)|"
        r"(?:hafizandaki |hafizadaki |kayitli )calismalarimizi (?:listele|goster)|"
        r"hafizanda (?:hangi calismalarimiz var|neler var))", prompt
    ):
        return None
    if authenticated is not True:
        return "Hesabına ait kalıcı çalışma kayıtlarını okumak için doğrulanmış giriş gerekli."

    lines = ["**CANO — hesabındaki kayıtlı çalışmalar**",
             "Bu döküm kayıt depolarından doğrudan okunur; yapay zekâ tahmini değildir."]
    sections = (
        ("Hafıza notları", memory_loader, None, None),
        ("Araştırma görevleri", research_loader, "title", "status"),
        ("Onaylı kuyruk", queue_loader, "goal", "state"),
        ("Son kod işleri (en fazla 10)", code_loader, "goal", "status"),
    )
    for label, load, title_key, status_key in sections:
        if load is None:
            lines.append(f"\n{label}: yapılandırılmamış.")
            continue
        try:
            records = load()
            if not isinstance(records, list) or not all(isinstance(r, Mapping) for r in records):
                raise ValueError("Invalid record listing")
            lines.append(f"\n{label}: {len(records)}")
            if title_key:
                for item in records[-10:]:
                    title = _literal(item.get(title_key), 160)
                    status = _literal(item.get(status_key), 40)
                    lines.append(f"- {title or 'Başlıksız kayıt'} — {status or 'durum belirtilmemiş'}")
                if len(records) > 10:
                    lines.append("Yalnızca son 10 kayıt gösteriliyor.")
        except Exception:
            lines.append(f"\n{label}: okunamadı; boş olduğu sonucuna varılamaz.")
    lines.append("\nNot: Bu liste yalnız bu CANO hesabının bağlı depolarını kapsar. "
                 "ChatGPT, Notion veya GitHub arşivindeki çalışmalar kendiliğinden aktarılmış sayılmaz. "
                 "Taslak veya kuyruk durumu, bilimsel doğrulama değildir.")
    return "\n".join(lines)
