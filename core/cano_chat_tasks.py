"""Explicit routing from CANO chat into the durable four-stage task runner."""
from __future__ import annotations


def parse_task_request(message):
    """Return a bounded task only when the user clearly invokes the team."""
    if not isinstance(message, str):
        return None
    text = message.strip()
    prefixes = ("cano görev:", "cano gorev:", "görev:", "gorev:")
    folded = text.casefold()
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
