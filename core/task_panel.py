"""Human-controlled task ledger UI; records work but never runs a model."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from core.task_store import ALLOWED_TRANSITIONS, TaskStore


def render_task_panel(st) -> None:
    with st.sidebar.expander("📋 Araştırma görevleri", expanded=False):
        st.caption(
            "Görevler bu sunucudaki SQLite dosyasına yerel/geçici olarak kaydedilir. "
            "Render ücretsiz diskinde yeniden dağıtım veya sunucu değişiminde kaybolabilir. "
            "Bu panel görevleri otomatik çalıştırmaz."
        )
        db_path = os.environ.get("AGENT_TASK_DB_PATH", "data/agent_tasks.sqlite3")
        try:
            store = TaskStore(Path(db_path))
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
        for task in tasks[-30:]:
            st.text(f"{task['title']} — {task['status']}")
            if task["goal"]:
                st.text("Hedef: " + task["goal"])
            if task["blockers"]:
                st.text("Engel: " + "; ".join(task["blockers"]))
            if task["evidence"]:
                st.text("Kanıt notları: " + "; ".join(task["evidence"]))

            next_statuses = sorted(ALLOWED_TRANSITIONS[task["status"]])
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

