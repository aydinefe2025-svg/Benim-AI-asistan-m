"""Explicit routing from CANO chat into the durable four-stage task runner."""
from __future__ import annotations


def parse_task_request(message):
    """Return a bounded task only when the user clearly invokes the team."""
    if not isinstance(message, str):
        return None
    text = message.strip()
    prefixes = ("cano görev:", "cano gorev:", "görev:", "gorev:")
    folded = text.casefold()
    if any(phrase in folded for phrase in (
            "kendini geliştir", "kendini gelistir",
            "öğrenmeye başla", "ogrenmeye basla")):
        return ("CANO için ölçülebilir gelişim önerisi hazırla: inceleme bekleyen "
                "taslaklarla doğrulanmış dersleri ayır; geliştirme ölçütü ve güvenli "
                "deney öner. Model ağırlıklarını, kayıtları veya etkin ajanları "
                "değiştirme; önerileri otomatik uygulama.")
    for prefix in prefixes:
        if folded.startswith(prefix):
            task = text[len(prefix):].strip()
            return task if 1 <= len(task) <= 1200 else None
    return None


def format_task_result(result):
    """Present saved role outputs with the real execution status and ID."""
    if not isinstance(result, dict) or not isinstance(result.get("stages"), list):
        raise ValueError("Invalid mission result")
    lines = [
        f"CANO görev kaydı: {result.get('id')}",
        f"Durum: {result.get('status')} · Bu istekteki yeni model çağrısı: {result.get('model_calls', 0)}",
        "Bu dört aşama model metni üretir; web, kod veya hesap makinesi çalıştırıldığı anlamına gelmez.",
    ]
    for stage in result["stages"]:
        if isinstance(stage, dict):
            lines.extend((f"\n### {stage.get('role', 'Aşama')}",
                          str(stage.get("output", ""))))
    lines.append("\nSonuç inceleme bekleyen taslaktır; kabul edilmiş veya bağımsız doğrulanmış sayılmaz.")
    return "\n".join(lines)


def stage_execution_notice(stage):
    """Flag historical outputs that predate the recorded text-only boundary."""
    if not isinstance(stage, dict):
        raise ValueError("Invalid mission stage")
    if stage.get("execution_mode") == "model_text_only":
        return None
    return ("Bu eski aşamada gerçek araç çalıştırma kaydı yok. Metindeki "
            "‘çalıştırdım’, ‘denedim’ veya ‘ölçtüm’ ifadeleri doğrulanmış "
            "deney sonucu değildir.")
