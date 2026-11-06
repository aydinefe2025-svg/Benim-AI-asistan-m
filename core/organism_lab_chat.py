"""Ground organism-lab chat answers in verified archived simulation records."""
from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", str(text)).casefold().replace("i\u0307", "i")


def is_organism_lab_question(message: str) -> bool:
    normalized = _normalize(message)
    markers = (
        "laboratuvar", "labaratuvar", "organizma laboratuvar", "organizma lab",
        "organizmalar laboratuvar", "organizmalar lab", "genom karşılaştır",
        "genom karsilastir", "genom deneyi", "dijital dünya", "dijital dunya",
        "dijital deney",
    )
    if any(marker in normalized for marker in markers):
        return True
    # A bare scientific term such as "genom nedir?" stays a normal model question.
    return (
        ("simülasyon" in normalized or "simulasyon" in normalized)
        and any(term in normalized for term in ("laboratuvar", "organizm", "genom", "deney"))
    )


def organism_lab_chat_reply(
    message: str,
    *,
    load_records: Callable[[], list[Mapping]] | None = None,
    session_result: Mapping | None = None,
) -> str | None:
    """Return a deterministic explanation for lab questions, never model guesses."""
    if not is_organism_lab_question(message):
        return None

    if load_records is not None:
        try:
            records = load_records()
        except Exception:
            return (
                "Laboratuvar arşivine şu anda güvenli biçimde erişemedim. "
                "Bu nedenle kayıtlı deney sonucunu doğrulayamadım ve tahmin etmiyorum. "
                "Laboratuvar panelindeki kalıcı deney geçmişini yenileyip tekrar deneyin."
            )
        for record in records or []:
            kind = record.get("kind")
            document = record.get("document")
            if not isinstance(document, Mapping):
                continue
            if kind == "campaign":
                from core.organism_lab_panel import explain_campaign

                try:
                    explanation = explain_campaign(document)
                except (KeyError, TypeError, ValueError):
                    continue
                return (
                    "Arşivdeki son genom karşılaştırması (yalnızca dijital simülasyon):\n\n"
                    + explanation
                )
            if kind == "world":
                values = (
                    document.get("robots"),
                    document.get("organisms"),
                    document.get("successful_routes"),
                )
                if all(type(value) is int and value >= 0 for value in values):
                    return (
                        "Arşivdeki son dijital dünya simülasyonu:\n"
                        f"- Sanal robot: {values[0]}\n"
                        f"- Sanal organizma: {values[1]}\n"
                        f"- Başarılı sanal rota: {values[2]}\n\n"
                        "Bunlar seçilen kurallarla çalışan yazılım simülasyonunun çıktılarıdır; "
                        "gerçek robot veya canlı ölçümü değildir."
                    )

    if isinstance(session_result, Mapping):
        try:
            from core.organism_lab_panel import explain_campaign

            report = session_result.get("report")
            if isinstance(report, Mapping):
                return (
                    "Bu oturumdaki, henüz kalıcı arşivden doğrulanmamış genom karşılaştırması:\n\n"
                    + explain_campaign(report)
                    + "\n\nBu sonuç gerçek biyolojik kanıt değildir."
                )
        except (KeyError, TypeError, ValueError):
            pass

    return (
        "Bu sohbette okunabilir bir laboratuvar sonucu bulunamadı; sonuç uydurmayacağım. "
        "Sol menüde Organizmalar Laboratuvarı bölümünü açıp simülasyonu çalıştırın. "
        "Kalıcı deney geçmişinde görünen kayıtlar daha sonra sohbetten açıklanabilir. "
        "Bu araç dijital simülasyon yürütür; gerçek hücre veya robot deneyi yapmaz."
    )
