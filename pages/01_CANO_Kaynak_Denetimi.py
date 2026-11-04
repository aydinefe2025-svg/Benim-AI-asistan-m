"""CANO auditable source quote review, accessible via Streamlit Pages."""
import os
import json
from pathlib import Path
import streamlit as st
from core.authentication import render_auth_gate
from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission
from core.task_panel import _session_database_path
from core.claim_evidence import audit_claim_quotes
from core.groq_team import generate_team_stage, TeamRateLimitError
from core.cano_command_center import _snapshot
from core.colony_postgres import ColonySnapshotStore
from core.targeted_research import execute_targeted_research
from core.scientific_sources import scientific_sources

st.set_page_config(page_title="CANO Kanıt Denetimi", page_icon="📑")
owner = render_auth_gate(st, os.environ)
st.title("CANO Kaynak–İddia Denetimi")
st.caption("Bilimsel kaynaktan gerçekten okunan alıntıları kontrol eder; alıntı bulunması iddiayı doğrulamaz.")
base = os.environ.get("AGENT_COLONY_DB_PATH", "data/agent_colony.sqlite3")
colony = AgentColony(_session_database_path(st, base), max_agents=12)
manager = CollaborativeMission(colony)
with colony._db() as db:
    missions = db.execute("SELECT id,task FROM colony_missions WHERE status=? ORDER BY created_at DESC LIMIT 12", ("review_pending",)).fetchall()
if not missions:
    st.info("Önce ana CANO ekranında araştırma görevi ve kaynak okuma işlemini tamamlayın.")
    st.stop()
mission_ids = [m["id"] for m in missions]
labels = {m["id"]: m["task"][:70] for m in missions}
mid = st.selectbox("Kaynağı okunmuş görev", mission_ids, format_func=lambda key: labels[key])
record = manager.get(mid)
documents = record["stages"][0].get("source_documents", [])
for source in documents:
    st.caption(str(source.get("status", "metadata_only")) + " · " + str(source.get("doi", "")))
    if source.get("excerpt"):
        st.text(source["excerpt"][:900])
key = os.environ.get("GROQ_API_KEY")
if not key:
    try:
        key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        key = None

class Client:
    def chat(self, model, system, prompt):
        return generate_team_stage(system + "\n\n" + prompt, api_key=key)

if documents and key and st.button("İddiaları kaynak alıntılarıyla karşılaştır (1 model çağrısı)"):
    try:
        if owner:
            store = ColonySnapshotStore(os.environ["DATABASE_URL"])
            store.initialize()
            store.save_versioned_verified(owner, _snapshot(colony))
        audit_claim_quotes(manager, mid, client=Client(), model="configured-provider")
        if owner:
            store.save_versioned_verified(owner, _snapshot(colony))
        st.rerun()
    except (ValueError, RuntimeError, TeamRateLimitError) as err:
        st.warning("Alıntı denetimi tamamlanamadı; önceki kayıtlar korunuyor.")
if not key:
    st.warning("Model bağlantısı yok; yeni iddia denetimi çalıştırılmadı.")
for item in manager.get(mid)["stages"][0].get("source_claim_audit", []):
    if item["status"] == "quote_found_unverified":
        st.success("Alıntı kaynakta bulundu; iddianın doğruluğu henüz kanıtlanmadı.")
        st.caption(item["claim"] + " — " + item["doi"])
        st.code(item["quote"])
        st.link_button("Kaynağı aç", item["citation_url"])
    else:
        st.warning("Önerilen alıntı ilgili kaynakta bulunmadı.")
        st.caption(item["claim"])
st.caption("Bu oturumun kaynak denetimi kayıtlarını saklamak için yedek alın.")
if not owner:
    st.download_button("Kaynak denetimini JSON yedekle",
                       data=json.dumps(_snapshot(colony), ensure_ascii=False, indent=2),
                       file_name="cano-claim-evidence.json", mime="application/json")

