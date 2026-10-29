"""Local UI for the personal research ledger.

Run with: streamlit run research_dashboard.py
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from core.knowledge_store import KnowledgeStore
from core.ollama_client import OllamaClient, OllamaError
from core.research_orchestrator import ResearchOrchestrator
from core.task_store import TaskStore

st.set_page_config(page_title="Büyük Sistem | Araştırma Merkezi", layout="wide")
st.title("🧠 Büyük Sistem — Araştırma Merkezi")
st.caption("Görevler, kaynaklar ve kanıt kayıtları. Bir kayıt, kendi başına doğrulanmış bilimsel sonuç anlamına gelmez.")

db_path = os.environ.get("BUYUK_SISTEM_DB", "data/research_system.sqlite3")
Path(db_path).parent.mkdir(parents=True, exist_ok=True)
tasks = TaskStore(db_path)
knowledge = KnowledgeStore(db_path)

tab_tasks, tab_sources, tab_claims, tab_research = st.tabs(["Görev Merkezi", "Kaynak Kasası", "İddia ve Kanıtlar", "Yerel AI Araştırması"])

with tab_tasks:
    st.subheader("Yeni görev")
    with st.form("new_task", clear_on_submit=True):
        title = st.text_input("Görev başlığı")
        goal = st.text_area("Hedef / beklenen çıktı")
        submitted = st.form_submit_button("Görevi kaydet")
    if submitted:
        try:
            tasks.create(title, goal)
            st.success("Görev kaydedildi.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    current_tasks = tasks.list()
    st.subheader(f"Görevler ({len(current_tasks)})")
    if current_tasks:
        for task in current_tasks:
            with st.expander(f"{task['status'].upper()} · {task['title']}"):
                st.write(task.get("goal") or "Hedef açıklaması girilmemiş.")
                st.caption(f"ID: {task['id']} · Güncelleme: {task['updated_at']}")
                if task["evidence"]:
                    st.write("Kanıtlar")
                    for evidence in task["evidence"]:
                        st.write(f"- {evidence}")
                if task["blockers"]:
                    st.warning("Engeller: " + "; ".join(task["blockers"]))
                with st.form(f"update_{task['id']}"):
                    status = st.selectbox(
                        "Durum", ["planned", "running", "blocked", "done", "verified"],
                        index=["planned", "running", "blocked", "done", "verified"].index(task["status"]),
                        key=f"status_{task['id']}",
                    )
                    note = st.text_input("İşlem notu", key=f"note_{task['id']}")
                    evidence = st.text_input("Kanıt (verified için zorunlu)", key=f"evidence_{task['id']}")
                    blocker = st.text_input("Engel (varsa)", key=f"blocker_{task['id']}")
                    save = st.form_submit_button("Durumu güncelle")
                if save:
                    try:
                        tasks.transition(
                            task["id"], status, note=note,
                            evidence=[evidence] if evidence.strip() else [],
                            blockers=[blocker] if blocker.strip() else ([] if status != "blocked" else task["blockers"]),
                        )
                        st.success("Durum güncellendi.")
                        st.rerun()
                    except (ValueError, KeyError) as exc:
                        st.error(str(exc))
    else:
        st.info("Henüz görev yok. İlk görevi yukarıdan ekleyebilirsin.")

with tab_sources:
    st.subheader("Kaynak kaydet")
    with st.form("new_source", clear_on_submit=True):
        source_url = st.text_input("HTTP(S) kaynak URL'si")
        source_title = st.text_input("Başlık")
        publisher = st.text_input("Yayıncı / kurum")
        published_at = st.text_input("Yayın tarihi (biliniyorsa)")
        source_notes = st.text_area("Notlar")
        source_text = st.text_area("İsteğe bağlı metin (SHA-256 özeti hesaplanır)")
        add_source = st.form_submit_button("Kaynağı kaydet")
    if add_source:
        try:
            knowledge.add_source(
                source_url, source_title, publisher=publisher,
                published_at=published_at, content=source_text, notes=source_notes,
            )
            st.success("Kaynak kaydedildi.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    sources = knowledge.list_sources()
    st.subheader(f"Kayıtlı kaynaklar ({len(sources)})")
    if sources:
        st.dataframe(
            [{
                "ID": s["id"], "Başlık": s["title"], "Yayıncı": s["publisher"],
                "URL": s["url"], "Yayın tarihi": s["published_at"],
                "SHA-256": s["content_sha256"], "Not": s["notes"],
            } for s in sources],
            use_container_width=True, hide_index=True,
        )
    else:
        st.info("Henüz kaynak kaydedilmedi.")

with tab_claims:
    st.subheader("Kaynaklara bağlı iddia kaydet")
    sources = knowledge.list_sources()
    if not sources:
        st.info("Önce Kaynak Kasası sekmesinden en az bir kaynak ekle.")
    else:
        source_options = {f"#{s['id']} — {s['title']}": s["id"] for s in sources}
        with st.form("new_claim", clear_on_submit=True):
            claim_text = st.text_area("Sınanabilir iddia")
            chosen_sources = st.multiselect("Kaynaklar", list(source_options.keys()))
            relationship = st.selectbox("Seçili kaynakların ilişkisi", ["supports", "contradicts", "context"])
            claim_status = st.selectbox("İnceleme durumu", ["unreviewed", "supported", "contested", "rejected"])
            confidence = st.slider("Ön değerlendirme güven puanı (kalibre olasılık değildir)", 0.0, 1.0, 0.5, 0.05)
            add_claim = st.form_submit_button("İddiayı kaydet")
        if add_claim:
            try:
                ids = [source_options[label] for label in chosen_sources]
                relationships = {source_id: relationship for source_id in ids}
                knowledge.add_claim(
                    claim_text, ids, status=claim_status,
                    confidence=confidence, relationships=relationships,
                )
                st.success("İddia ve kaynak bağlantıları kaydedildi.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))

    claims = knowledge.list_claims()
    st.subheader(f"Kayıtlı iddialar ({len(claims)})")
    for claim in claims:
        with st.expander(f"{claim['status'].upper()} · {claim['claim']}"):
            st.write(f"Güven puanı: {claim['confidence']:.2f} (kalibre olasılık değildir)")
            details = knowledge.get_claim(claim["id"])
            for source in details["sources"]:
                st.write(f"- [{source['title']}]({source['url']}) — {source['relationship']}")


with tab_research:
    st.subheader("Yerel Ollama ile araştırma taslağı")
    st.caption("Bu akış planlayıcı → şüpheci denetçi → sentezleyici rollerini çalıştırır. Web araması yapmaz; aynı model üç rolde kullanılırsa bağımsız çoklu-model doğrulaması değildir.")
    with st.form("local_research", clear_on_submit=False):
        question = st.text_area("Araştırma sorusu", placeholder="Örn. Cezerî'nin mekanizmalarında hangi kontrol ilkeleri belgelenmiştir?")
        ollama_url = st.text_input("Ollama adresi", value=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
        model = st.text_input("Model adı", value=os.environ.get("OLLAMA_MODEL", "qwen3:8b"))
        run_research = st.form_submit_button("Araştırmayı çalıştır")
    if run_research:
        try:
            client = OllamaClient(ollama_url, timeout=180)
            available_models = client.list_models()
            if model not in available_models:
                st.error("Model Ollama'da görünmüyor. Kurulu modeller: " + (", ".join(available_models) or "(model bulunamadı)"))
            else:
                with st.spinner("Planlama, şüpheci denetim ve sentez çalışıyor..."):
                    result = ResearchOrchestrator(
                        client, task_store=tasks, output_dir="reports"
                    ).run(question, research_model=model)
                st.session_state["last_research_report"] = result["report"]
                st.session_state["last_research_path"] = result["report_path"]
                st.session_state["last_research_task"] = result["task_id"]
                st.success("Taslak rapor üretildi ve görev kaydına bağlandı.")
        except (ValueError, KeyError, OSError, RuntimeError, OllamaError) as exc:
            st.error(f"Yerel araştırma çalışmadı: {exc}")
    if st.session_state.get("last_research_report"):
        st.caption(
            f"Görev: {st.session_state.get('last_research_task')} · "
            f"Rapor dosyası: {st.session_state.get('last_research_path')}"
        )
        st.markdown(st.session_state["last_research_report"])
