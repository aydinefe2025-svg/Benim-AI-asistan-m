"""Role-based local research workflow with explicit evidence limits."""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path
from typing import Protocol

from core.task_store import TaskStore


class ChatClient(Protocol):
    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str: ...


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value[:64]).strip("-").lower()
    return slug or "research"


class ResearchOrchestrator:
    """Runs planner → skeptic → synthesis passes and records the run.

    This is role-separated review, not proof of independent consensus. If the
    same model is used for every role, the report says so explicitly. No web
    search or source fetching is performed by this module.
    """

    def __init__(
        self,
        client: ChatClient,
        *,
        task_store: TaskStore,
        output_dir: str | Path = "reports",
    ) -> None:
        self.client = client
        self.task_store = task_store
        self.output_dir = Path(output_dir)

    def run(
        self,
        question: str,
        *,
        research_model: str = "qwen3:8b",
        skeptic_model: str | None = None,
        synthesis_model: str | None = None,
    ) -> dict[str, str]:
        question = question.strip()
        if not question:
            raise ValueError("Research question cannot be empty")
        skeptic_model = skeptic_model or research_model
        synthesis_model = synthesis_model or research_model
        models = [research_model, skeptic_model, synthesis_model]
        task = self.task_store.create(
            f"Yerel araştırma: {question[:120]}",
            "Planla, karşı kanıtları denetle ve sınırlamaları açık bir sentez üret.",
        )
        self.task_store.transition(task["id"], "running", note="Local Ollama role-pass workflow started")
        rules = (
            "Kaynak uydurma. Web'e eriştiğini veya kaynakları okuduğunu iddia etme. "
            "Elinde kaynak pasajı yoksa bunu açıkça söyle. Olguları, çıkarımları ve "
            "bilinmeyenleri ayır. Karşı görüşleri ve hangi kanıtın sonucu değiştireceğini belirt. "
            "Yanıtı Türkçe ver."
        )
        try:
            plan = self.client.chat(
                research_model,
                "Sen araştırma planlayıcısısın. " + rules,
                "Soruyu alt sorulara ayır. Gerekli birincil kaynakları, ölçümleri, "
                "hesapları ve doğrulama adımlarını sırala. Kaynak bulmuş gibi davranma.\n\n"
                f"ARAŞTIRMA SORUSU: {question}",
            )
            critique = self.client.chat(
                skeptic_model,
                "Sen şüpheci metodoloji denetçisisin. " + rules,
                "Aşağıdaki planı eleştir: varsayımlar, karşı açıklamalar, eksik kanıt, "
                "yanlışlanabilir testler ve başarısızlık ihtimalleri.\n\n"
                f"SORU: {question}\n\nPLAN:\n{plan}",
            )
            synthesis = self.client.chat(
                synthesis_model,
                "Sen kanıt sınırlarını koruyan bilimsel editörsün. " + rules,
                "Plan ve eleştiriyi sentezle. Şu başlıkları kullan: Özet, Desteklenen "
                "çıkarımlar, Bilinmeyenler, Karşı görüş, Güven düzeyi, Kaynak gereksinimi, "
                "Sonraki doğrulama. Kaynak uydurma.\n\n"
                f"SORU: {question}\n\nPLAN:\n{plan}\n\nDENETİM:\n{critique}",
            )
            self.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            filename = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{_slug(question)}.md"
            output_path = self.output_dir / filename
            same_model = len(set(models)) == 1
            report = f"""# Yerel Araştırma Raporu

- Oluşturulma: {stamp}
- Soru: {question}
- Araştırma modeli: {research_model}
- Şüpheci denetçi modeli: {skeptic_model}
- Sentez modeli: {synthesis_model}
- Aynı model tüm rollerde: {"Evet; bu bağımsız çoklu-model doğrulaması değildir." if same_model else "Hayır; yine de farklı model kullanımı tek başına bağımsız kanıt sayılmaz."}
- Web/kaynak erişimi: Bu iş akışı web araması yapmadı ve kaynak metni indirmedi.
- Durum: Rol tabanlı taslak; kaynaklarla dış doğrulama bekliyor.

## 1. Araştırma planı

{plan}

## 2. Şüpheci denetim

{critique}

## 3. Sentez

{synthesis}

## Doğrulama sınırı

Bu rapor, yerel modelin ürettiği bir plan/eleştiri/sentez kaydıdır. Kaynakların doğrulandığı, deneyin yapıldığı veya bilimsel sonucun kanıtlandığı anlamına gelmez.
"""
            output_path.write_text(report, encoding="utf-8")
            self.task_store.transition(
                task["id"], "done",
                note="Three role passes completed; source verification still required",
                evidence=[f"Report artifact: {output_path.as_posix()}", f"Models used: {', '.join(models)}"],
            )
            return {
                "task_id": task["id"],
                "report_path": output_path.as_posix(),
                "research_model": research_model,
                "skeptic_model": skeptic_model,
                "synthesis_model": synthesis_model,
                "same_model_all_roles": str(same_model).lower(),
                "report": report,
            }
        except Exception as exc:
            self.task_store.transition(
                task["id"], "blocked",
                note="Local research workflow failed",
                blockers=[str(exc)],
            )
            raise
