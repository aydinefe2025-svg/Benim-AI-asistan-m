"""User-controlled task panel; no autonomous execution or paid services."""
import os
from pathlib import Path

from core.task_store import TaskStore


def render_task_panel(st):
    with st.sidebar.expander("📋 Araştırma görevleri", expanded=False):
        st.caption(
            "Görevler yalnızca bu sunucunun SQLite dosyasına kaydedilir. "
            "Render ücretsiz diskinde yeniden dağıtım sonrası kaybolabilir. "
            "Görev oluşturmak, otomatik olarak çalıştırmak anlamına gelmez."
        )
        db_path = os.environ.get("AGENT_TASK_DB_PATH", "data/research_system.sqlite3")
        try:
            store = TaskStore(Path(db_path))
        except (OSError, ValueError) as exc:
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

        tasks = store.list()
        st.caption(f"Yerel kayıt sayısı: {len(tasks)}")
        for task in tasks[-30:]:
            st.markdown(f"**{task['title']}** — `{task['status']}`")
            if task["blockers"]:
                st.caption("Engel: " + "; ".join(task["blockers"]))
            if task["evidence"]:
                st.caption("Kanıt: " + "; ".join(task["evidence"]))
