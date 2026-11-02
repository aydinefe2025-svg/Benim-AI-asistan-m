"""Human-triggered task ledger and bounded research draft UI."""
from __future__ import annotations

import os
import sqlite3
import uuid
from pathlib import Path

from core.task_store import ALLOWED_TRANSITIONS, TaskStore
from core.research_import import import_research_archive
from core.research_export import export_research_archive
from core.research_drafts import save_draft, load_draft
from core.agent_executor import run_research_task


def _session_database_path(st, configured_path: str) -> Path:
    """Isolate task drafts by Streamlit session on the public shared app."""
    session_id = st.session_state.get("agent_task_session_id")
    if not isinstance(session_id, str) or len(session_id) != 32 or any(
        char not in "0123456789abcdef" for char in session_id
    ):
        session_id = uuid.uuid4().hex
        st.session_state["agent_task_session_id"] = session_id
    base = Path(configured_path)
    suffix = base.suffix or ".sqlite3"
    return base.with_name(f"{base.stem}.{session_id}{suffix}")


def render_task_panel(st, answer=None) -> None:
    with st.sidebar.expander("📋 Araştırma görevleri", expanded=False):
        st.caption(
            "Görevler yalnızca bu tarayıcı oturumuna ait SQLite dosyasına yerel/geçici olarak kaydedilir. "
            "Render ücretsiz diskinde yeniden dağıtım veya sunucu değişiminde kaybolabilir. "
            "Araştırma yalnızca kullanıcı düğmeye bastığında çalışır; sonuç doğrulanmamış taslaktır."
        )
        db_path = os.environ.get("AGENT_TASK_DB_PATH", "data/agent_tasks.sqlite3")
        try:
            store = TaskStore(_session_database_path(st, db_path))
        except (OSError, ValueError, sqlite3.Error):
            st.error("Görev veritabanı açılamadı; kayıt yapılmadı.")
            return

        with st.form("agent_task_create", clear_on_submit=True):
            title = st.text_input("Görev adı", max_chars=200)
            goal = st.text_area("Başarı hedefi", max_chars=1000)
            submitted = st.form_submit_button("Görevi kaydet")
        if submitted:
            try:
                task = store.create(title, goal)
                st.success(f"Görev kaydedildi: {task['id'][:8]}")
            except ValueError:
                st.warning("Görev adı boş olamaz.")

        backup_upload = st.file_uploader(
            "Araştırma yedeğini geri yükle (JSON)",
            type=["json"], key="research_archive_upload",
        )
        if st.button("Yedeği ayrı görevler olarak içe aktar", key="import_research_tasks"):
            if backup_upload is None:
                st.warning("Önce JSON yedeğini seçin.")
            else:
                try:
                    imported = import_research_archive(store, backup_upload.getvalue())
                    st.success(f"{imported} görev içe aktarıldı. Eski kayıtlar korunuyor.")
                except (ValueError, OSError):
                    st.error("Yedek geçersiz veya veritabanı erişilemiyor; içe aktarma yapılamadı.")
        tasks = store.list()
        st.caption(f"Yerel kayıt sayısı: {len(tasks)}")
        st.caption("Kaynak doğrulama mekanizması eklenene kadar görevler Doğrulandı durumuna alınamaz.")
        try:
            archive = export_research_archive(store)
            st.download_button(
                "Görevleri ve taslakları yedekle (JSON)",
                data=archive,
                file_name="arastirma-gorevleri-yedek.json",
                mime="application/json",
                key="download_research_tasks",
            )
        except (ValueError, OSError, sqlite3.Error):
            st.warning("Araştırma yedeği oluşturulamadı.")
        for task in tasks[-30:]:
            st.text(f"{task['title']} — {task['status']}")
            if task["goal"]:
                st.text("Hedef: " + task["goal"])
            if task["blockers"]:
                st.text("Engel: " + "; ".join(task["blockers"]))
            if task["evidence"]:
                st.text("Kanıt notları: " + "; ".join(task["evidence"]))

            draft = load_draft(store.db_path, task["id"])
            if draft:
                st.text_area("Doğrulanmamış araştırma taslağı", value=draft,
                             height=160, disabled=True, key="draft_" + task["id"])
            if answer is not None and task["status"] in {"planned", "blocked"}:
                if st.button("Araştırmayı çalıştır", key="run_" + task["id"]):
                    result = run_research_task(store, task["id"], answer)
                    if result["status"] == "done":
                        save_draft(store.db_path, task["id"], result["draft"])
                        st.success("Taslak kaydedildi; kaynak doğrulaması gerekiyor.")
                    else:
                        st.warning("Araştırma sağlayıcısı başarısız oldu; görev engellendi.")
                    st.rerun()

            # Source verification is not implemented yet. Do not let arbitrary
            # user-entered text promote a task to verified.
            next_statuses = sorted(ALLOWED_TRANSITIONS[task["status"]] - {"verified"})
            if not next_statuses:
                continue
            with st.form("agent_task_transition_" + task["id"]):
                next_status = st.selectbox(
                    "Yeni durum", next_statuses, key="task_status_" + task["id"]
                )
                note = st.text_input("Durum notu", key="task_note_" + task["id"])
                evidence = st.text_input(
                    "Kanıt / kaynak URL'si (doğrulama için zorunlu)",
                    key="task_evidence_" + task["id"],
                )
                blocker = st.text_input(
                    "Engel (varsa)", key="task_blocker_" + task["id"]
                )
                changed = st.form_submit_button("Durumu güncelle")
            if changed:
                try:
                    store.transition(
                        task["id"],
                        next_status,
                        note=note,
                        evidence=[evidence] if evidence.strip() else None,
                        blockers=[blocker] if blocker.strip() else None,
                    )
                    st.success("Görev durumu güncellendi.")
                    st.rerun()
                except (KeyError, ValueError, sqlite3.Error):
                    st.warning("Durum güncellenemedi; görev yeniden okunup kontrol edilmeli.")

