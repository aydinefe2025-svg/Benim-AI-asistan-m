"""Explicitly operated Streamlit UI for persistent bounded agent colony."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from core.agent_colony import AgentColony
from core.task_panel import _session_database_path


class AnswerAdapter:
    def __init__(self, answer):
        self.answer = answer

    def chat(self, model, system, prompt):
        return self.answer(system + "\n\n" + prompt)


def render_colony_panel(st, answer=None):
    with st.sidebar.expander("🧬 Öğrenen uzman ajanlar", expanded=False):
        st.caption(
            "Ajanlar yapılandırılmış uzman örnekleridir; kendi kendine çalışan süreçler "
            "veya eğitilmiş yeni modeller değildir. İşlemler yalnızca düğmeye basınca çalışır. "
            "Kayıtlar oturuma özel geçici SQLite dosyasındadır; JSON yedeği alın.")
        base = os.environ.get("AGENT_COLONY_DB_PATH", "data/agent_colony.sqlite3")
        try:
            colony = AgentColony(_session_database_path(st, base), max_agents=12)
            with colony._db() as db:
                agents = [dict(row) for row in db.execute(
                    "SELECT id,role,generation,parent_id FROM colony_agents ORDER BY created_at,id")]
        except (OSError, ValueError, sqlite3.Error):
            st.error("Ajan veritabanı açılamadı.")
            return
        if not agents:
            if st.button("Kurucu araştırma ajanını oluştur", key="colony_founder"):
                try:
                    colony.create_founder(
                        "research", "You are a careful Turkish research agent. "
                        "Separate verified facts from assumptions and draft claims.")
                    st.rerun()
                except (RuntimeError, ValueError, sqlite3.Error):
                    st.error("Kurucu ajan oluşturulamadı.")
            return

        labels = {a["id"]: f"{a['role']} (nesil {a['generation']}, {a['id'][:8]})"
                  for a in agents}
        selected = st.selectbox("Uzman ajan", list(labels), format_func=lambda k: labels[k],
                                key="colony_agent_select")
        with st.form("colony_spawn_form"):
            role = st.text_input("Yeni uzmanlık", max_chars=80)
            instructions = st.text_area("Yeni ajanın görevi", max_chars=1000)
            spawn = st.form_submit_button("Uzman ajan oluştur")
        if spawn:
            try:
                child = colony.spawn(selected, role, instructions, approved=True)
                st.success("Uzman ajan kaydedildi: " + child[:8])
                st.rerun()
            except (ValueError, RuntimeError, PermissionError, sqlite3.Error):
                st.warning("Ajan oluşturulamadı; kota veya alanları kontrol edin.")

        with st.form("colony_feedback_form"):
            task = st.text_input("Dersin ilişkili olduğu görev", max_chars=300)
            lesson = st.text_area("Öğrenilecek ders", max_chars=1000)
            evidence = st.text_input("İnceleme/kanıt referansı", max_chars=300)
            accepted = st.checkbox("Bu dersi sonraki görevlerde kullanmayı onaylıyorum")
            save = st.form_submit_button("Dersi kaydet")
        if save:
            try:
                colony.feedback(selected, task, lesson, evidence, accepted=accepted)
                st.success("Ders kaydedildi." if accepted else "Ders inceleme bekliyor.")
            except (ValueError, sqlite3.Error, KeyError):
                st.warning("Ders kaydedilemedi.")

        st.caption(f"Kabul edilmiş ders: {len(colony.lessons(selected, limit=20))} (son 20)")
        if answer is None:
            st.warning("Görev yürütmek için model sağlayıcısı gerekli.")
        else:
            with st.form("colony_run_form"):
                goal = st.text_area("Ajana verilecek görev", max_chars=1200)
                run = st.form_submit_button("Uzmanı çalıştır")
            if run:
                try:
                    result = colony.run(selected, goal, client=AnswerAdapter(answer),
                                        model="configured-provider")
                    st.session_state["colony_last_draft"] = result["output"]
                    st.success("Taslak üretildi; bağımsız doğrulama gerekiyor.")
                except (RuntimeError, ValueError, OSError):
                    st.error("Ajan görevi tamamlayamadı.")
        if st.session_state.get("colony_last_draft"):
            st.text_area("Son doğrulanmamış taslak",
                         value=st.session_state["colony_last_draft"],
                         height=200, disabled=True)
        with colony._db() as db:
            data = {"agents": [dict(row) for row in db.execute(
                "SELECT * FROM colony_agents ORDER BY created_at,id")],
                    "feedback": [dict(row) for row in db.execute(
                "SELECT * FROM colony_feedback ORDER BY id")]}
        import json
        st.download_button("Ajanları ve dersleri JSON yedekle",
                           data=json.dumps(data, ensure_ascii=False, indent=2),
                           file_name="ajan-kolonisi-yedek.json",
                           mime="application/json", key="colony_backup")
