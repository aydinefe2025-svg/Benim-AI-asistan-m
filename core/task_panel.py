"""User-controlled task panel; no autonomous execution or paid services."""
import os
from pathlib import Path

from core.task_store import TaskStore
from core.agent_executor import run_research_task
from core.research_drafts import save_draft, load_draft


def render_task_panel(st, groq_key=None):
    with st.sidebar.expander("📋 Araştırma görevleri", expanded=False):
        st.caption(
            "Görevler yalnızca bu sunucunun SQLite dosyasına kaydedilir. "
            "Render ücretsiz diskinde yeniden dağıtım sonrası kaybolabilir. "
            "Görev oluşturmak, otomatik olarak çalıştırmak anlamına gelmez."
        )
        db_path = os.environ.get("AGENT_TASK_DB_PATH", "data/agent_tasks.sqlite3")
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

        if groq_key:
            st.caption("Görev yürütme isteğe bağlıdır; model yanıtı doğrulanmamış taslaktır.")
            for task in tasks[-10:]:
                if task["status"] not in {"planned", "blocked"}:
                    continue
                if st.button("Araştırmayı çalıştır: " + task["title"][:45], key="run_" + task["id"]):
                    def ask_model(goal):
                        from groq import Groq
                        client = Groq(api_key=groq_key)
                        response = client.chat.completions.create(
                            model="openai/gpt-oss-120b",
                            messages=[
                                {"role": "system", "content": (
                                    "Türkçe araştırma taslağı oluştur. Kaynakları doğrulamadıysan "
                                    "doğruladığını iddia etme. Erişmediğin bağlantıları uydurma. "
                                    "Önerileri ve açık soruları ayır.")},
                                {"role": "user", "content": goal},
                            ],
                            max_tokens=1200,
                        )
                        return response.choices[0].message.content
                    result = run_research_task(store, task["id"], ask_model)
                    if result["status"] == "done":
                        save_draft(store.db_path, task["id"], result["draft"])
                        st.success("Taslak üretildi; bağımsız doğrulama bekliyor.")
                    else:
                        st.warning("Görev engellendi; bağlantıyı veya limiti kontrol edin.")
            for task in tasks[-10:]:
                draft = load_draft(store.db_path, task["id"])
                if draft:
                    st.markdown("**Taslak — " + task["title"] + "**")
                    st.markdown(draft)
