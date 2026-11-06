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
from core.task_recovery import recover_stale_running


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


def render_task_panel(st, answer=None, *, store_override=None) -> None:
    with st.sidebar.expander("📋 Araştırma görevleri", expanded=False):
        if store_override is not None:
            st.caption("Görevler giriş yapan hesabınıza ait kalıcı depoda tutulur. Araştırma yalnızca kullanıcı düğmeye bastığında çalışır; sonuç doğrulanmamış taslaktır.")
        else:
            st.caption("Görevler yalnızca bu tarayıcı oturumuna ait SQLite dosyasına yerel/geçici olarak kaydedilir. Render ücretsiz diskinde yeniden dağıtım veya sunucu değişiminde kaybolabilir. Araştırma yalnızca kullanıcı düğmeye bastığında çalışır; sonuç doğrulanmamış taslaktır.")
        try:
            if store_override is not None:
                store = store_override
                recovered = store.recover_stale_running(stale_after_seconds=3600)
            else:
                db_path = os.environ.get("AGENT_TASK_DB_PATH", "data/agent_tasks.sqlite3")
                store = TaskStore(_session_database_path(st, db_path))
                recovered = recover_stale_running(store.db_path, stale_after_seconds=3600)
        except Exception:
            st.error("Görev veritabanı açılamadı; kayıt yapılmadı.")
            return

        if recovered:
            st.warning(f"{len(recovered)} kesintiye uğramış görev güvenli şekilde engellendi; yeniden çalıştırmadan önce inceleyin.")

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
                except Exception:
                    st.error("Yedek geçersiz veya veritabanı erişilemiyor; içe aktarma yapılamadı.")
        tasks = store.list()
        st.caption(f"Yerel kayıt sayısı: {len(tasks)}")
        st.caption("Kaynak doğrulama mekanizması eklenene kadar görevler Doğrulandı durumuna alınamaz.")
        try:
            archive = export_research_archive(store)
            if store_override is None:
                st.download_button(
                    "Görevleri ve taslakları yedekle (şifrelenmemiş JSON)",
                    data=archive,
                    file_name="arastirma-gorevleri-yedek.json",
                    mime="application/json",
                    key="download_research_tasks",
                )
            else:
                st.caption("Hesap görevleri ve taslakları CANO Komuta Merkezi'ndeki "
                           "şifreli dış yedek paketine eklenir.")
        except Exception:
            st.warning("Araştırma yedeği oluşturulamadı.")
        for task in tasks[-30:]:
            st.text(f"{task['title']} — {'İnceleme bekliyor' if task['status'] == 'review_pending' else task['status']}")
            if task["goal"]:
                st.text("Hedef: " + task["goal"])
            if task["blockers"]:
                st.text("Engel: " + "; ".join(task["blockers"]))
            if task["evidence"]:
                st.text("Kanıt notları: " + "; ".join(task["evidence"]))

            draft = (store.load_draft(task["id"]) if hasattr(store, "load_draft")
                     else load_draft(store.db_path, task["id"]))
            if draft:
                st.text_area("Doğrulanmamış araştırma taslağı", value=draft,
                             height=160, disabled=True, key="draft_" + task["id"])
            if answer is not None and task["status"] in {"planned", "blocked"}:
                if st.button("Araştırmayı çalıştır", key="run_" + task["id"]):
                    result = run_research_task(store, task["id"], answer)
                    if result["status"] == "review_pending":
                        st.success("Taslak kaydedildi; kaynak doğrulaması gerekiyor.")
                    else:
                        st.warning("Araştırma sağlayıcısı başarısız oldu; görev engellendi.")
                    st.rerun()

            # Source verification is not implemented yet. Do not let arbitrary
            # user-entered text promote a task to verified.
            next_statuses = sorted(ALLOWED_TRANSITIONS.get(task["status"], set()) - {"verified"})
            if task["status"] not in ALLOWED_TRANSITIONS:
                st.warning("Bilinmeyen görev durumu; kayıt değiştirilmedi. Yönetici incelemesi gerekli.")
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
                except Exception:
                    st.warning("Durum güncellenemedi; görev yeniden okunup kontrol edilmeli.")

