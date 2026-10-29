"""Role-based local research workflow with explicit evidence limits."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Protocol

from core.knowledge_store import KnowledgeStore
from core.task_store import TaskStore
from core.web_search import SearchResult, SearchError, DuckDuckGoSearch


class ChatClient(Protocol):
    def chat(self, model: str, system: str, prompt: str, *, temperature: float = 0.2) -> str: ...


class SearchClient(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value[:64]).strip("-").lower()
    return slug or "research"


class ResearchOrchestrator:
    """Runs planner → skeptic → synthesis passes and records the run.

    This is role-separated review, not proof of independent consensus. If the
    same model is used for every role, the report says so explicitly. Web search
    is optional and returns snippets only; source pages are not fetched.
    """

    def __init__(
        self,
        client: ChatClient,
        *,
        task_store: TaskStore,
        output_dir: str | Path = "reports",
        knowledge_store: KnowledgeStore | None = None,
        search_client: SearchClient | None = None,
    ) -> None:
        self.client = client
        self.task_store = task_store
        self.output_dir = Path(output_dir)
        self.knowledge_store = knowledge_store
        self.search_client = search_client

    def run(
        self,
        question: str,
        *,
        research_model: str = "qwen3:8b",
        skeptic_model: str | None = None,
        synthesis_model: str | None = None,
        web_search: bool = False,
        max_search_results: int = 5,
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

        search_results: list[SearchResult] = []
        search_error = ""
        if web_search:
            searcher = self.search_client or DuckDuckGoSearch()
            try:
                search_results = searcher.search(question, max_results=max_search_results)
                if self.knowledge_store:
                    for result in search_results:
                        self.knowledge_store.add_source(
                            result.url,
                            result.title or result.url,
                            publisher=result.publisher,
                            notes=(
                                "Search result snippet only; full source page was not fetched or verified. "
                                f"Query: {question}\nSnippet: {result.snippet}"
                            ),
                        )
            except (SearchError, OSError, ValueError) as exc:
                search_error = str(exc)

        if search_results:
            search_context = "\n\n".join(
                f"[{i}] {item.title}\nURL: {item.url}\nPublisher: {item.publisher}\n"
                f"Search snippet only (not full source text): {item.snippet}"
                for i, item in enumerate(search_results, 1)
            )
        elif web_search:
            search_context = f"Web search was requested but no results were obtained. Error: {search_error or 'no results'}"
        else:
            search_context = "No web search was performed."

        rules = (
            "Kaynak uydurma. Arama sonucu snippet'lerini tam makale okumuş gibi sunma. "
            "Bir arama sonucu, iddianın doğrulandığı anlamına gelmez. Elinde kaynak pasajı "
            "yoksa bunu açıkça söyle. Olguları, çıkarımları ve bilinmeyenleri ayır. "
            "Karşı görüşleri ve hangi kanıtın sonucu değiştireceğini belirt. Türkçe yanıt ver."
        )
        try:
            plan = self.client.chat(
                research_model,
                "Sen araştırma planlayıcısısın. " + rules,
                "Soruyu alt sorulara ayır. Gerekli birincil kaynakları, ölçümleri, "
                "hesapları ve doğrulama adımlarını sırala. Kaynak bulmuş gibi davranma.\n\n"
                f"ARAŞTIRMA SORUSU: {question}\n\nARAMA SONUÇLARI:\n{search_context}",
            )
            critique = self.client.chat(
                skeptic_model,
                "Sen şüpheci metodoloji denetçisisin. " + rules,
                "Aşağıdaki planı ve arama sonuçlarını eleştir: varsayımlar, karşı açıklamalar, "
                "eksik kanıt, kaynak kalitesi, yanlışlanabilir testler ve başarısızlık ihtimalleri.\n\n"
                f"SORU: {question}\n\nARAMA SONUÇLARI:\n{search_context}\n\nPLAN:\n{plan}",
            )
            synthesis = self.client.chat(
                synthesis_model,
                "Sen kanıt sınırlarını koruyan bilimsel editörsün. " + rules,
                "Plan ve eleştiriyi sentezle. Şu başlıkları kullan: Özet, Desteklenen "
                "çıkarımlar, Bilinmeyenler, Karşı görüş, Güven düzeyi, Kaynak gereksinimi, "
                "Sonraki doğrulama. Arama snippet'lerini doğrulanmış kaynak gibi sunma.\n\n"
                f"SORU: {question}\n\nARAMA SONUÇLARI:\n{search_context}\n\n"
                f"PLAN:\n{plan}\n\nDENETİM:\n{critique}",
            )
            self.output_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
            filename = f"{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}-{_slug(question)}.md"
            output_path = self.output_dir / filename
            same_model = len(set(models)) == 1
            if search_results:
                source_list = "\n".join(
                    f"{i}. [{item.title}]({item.url}) — {item.publisher}\n"
                    f"   Search snippet only: {item.snippet}"
                    for i, item in enumerate(search_results, 1)
                )
                search_status = f"{len(search_results)} search results; source pages not fetched"
            elif web_search:
                source_list = f"No results captured. Error: {search_error or 'unknown search failure'}"
                search_status = "Search requested but failed"
            else:
                source_list = "Web search was not requested."
                search_status = "Not performed"
            report = f"""# Yerel Araştırma Raporu

- Oluşturulma: {stamp}
- Soru: {question}
- Araştırma modeli: {research_model}
- Şüpheci denetçi modeli: {skeptic_model}
- Sentez modeli: {synthesis_model}
- Aynı model tüm rollerde: {"Evet; bu bağımsız çoklu-model doğrulaması değildir." if same_model else "Hayır; yine de farklı model kullanımı tek başına bağımsız kanıt sayılmaz."}
- Web araması: {search_status}
- Durum: Rol tabanlı taslak; kaynak sayfaları ve iddialar dışarıdan doğrulanmalı.

## Arama sonuçları (snippet; kaynak sayfası okunmadı)

{source_list}

## 1. Araştırma planı

{plan}

## 2. Şüpheci denetim

{critique}

## 3. Sentez

{synthesis}

## Doğrulama sınırı

Arama sonuçları yalnızca keşif ipuçlarıdır; kaynak sayfalarının içeriği bu iş akışında indirilmedi. Bu rapor, yerel modelin ürettiği bir plan/eleştiri/sentez kaydıdır. Kaynakların doğrulandığı, deneyin yapıldığı veya bilimsel sonucun kanıtlandığı anlamına gelmez.
"""
            output_path.write_text(report, encoding="utf-8")
            evidence = [f"Report artifact: {output_path.as_posix()}", f"Models used: {', '.join(models)}"]
            if web_search:
                evidence.append(f"Web search results captured: {len(search_results)}")
                if search_error:
                    evidence.append(f"Web search error: {search_error}")
            self.task_store.transition(
                task["id"], "done",
                note="Role passes completed; source verification still required",
                evidence=evidence,
            )
            return {
                "task_id": task["id"],
                "report_path": output_path.as_posix(),
                "research_model": research_model,
                "skeptic_model": skeptic_model,
                "synthesis_model": synthesis_model,
                "same_model_all_roles": str(same_model).lower(),
                "search_count": str(len(search_results)),
                "search_error": search_error,
                "report": report,
            }
        except Exception as exc:
            self.task_store.transition(
                task["id"], "blocked",
                note="Local research workflow failed",
                blockers=[str(exc)],
            )
            raise
