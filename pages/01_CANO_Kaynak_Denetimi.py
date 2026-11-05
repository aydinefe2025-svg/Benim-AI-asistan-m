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
from core.groq_team import TeamRateLimitError
from core.groq_claim_json import generate_claim_quote_json
from core.cano_command_center import _snapshot
from core.colony_postgres import ColonySnapshotStore
from core.colony_restore import restore_owner_backup
from core.browser_colony import (
    browser_colony_component, browser_write_confirmed, encode_browser_colony_backup,
)
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
restore_notice = st.session_state.pop("_cano_evidence_restore_notice", None)
if restore_notice:
    st.warning(restore_notice)
if not missions:
    # A new Streamlit session creates a fresh, isolated SQLite file. Never
    # silently import another owner's data or overwrite a nonempty colony.
    # Recovery is explicit, authenticated and read back transactionally.
    with colony._db() as db:
        local_agent_count = db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]
    if owner and not local_agent_count:
        st.info("Bu oturumda kaynak denetimi görevi yok. Hesabınızın kalıcı yedeğini güvenli biçimde geri yükleyebilirsiniz.")
        if st.button("Hesabıma ait CANO yedeğini geri yükle", key="cano_evidence_restore"):
            try:
                store = ColonySnapshotStore(os.environ["DATABASE_URL"])
                store.verify_schema()
                restore_result = restore_owner_backup(
                    colony, store, owner, approved=True,
                    archive_incomplete_missions=True)
                restored = restore_result["agent_count"]
                skipped = restore_result["archived_incomplete_missions"]
            except ValueError:
                st.warning(
                    "Eski CANO yedeğinde geri yükleme için gerekli alanlar eksik; "
                    "mevcut kayıtlar ve kalıcı yedek korunuyor.")
            except (KeyError, LookupError, RuntimeError, OSError):
                st.warning("Hesabınıza ait yedek geri yüklenemedi; mevcut kayıtlar değiştirilmedi.")
            except Exception:
                st.error("Kalıcı yedek servisi kullanılamıyor; hiçbir kayıt değiştirilmedi.")
            else:
                st.success(f"{restored} CANO rol kaydı geri yüklendi; kaynak denetimi görevleri yeniden okunuyor.")
                if skipped:
                    st.session_state["_cano_evidence_restore_notice"] = (
                        f"{skipped} eksik eski görev kaydı mevcut görev tablosuna alınamadı. "
                        "Özgün yedek, sürüm geçmişine arşivlendi ve korunuyor.")
                st.rerun()
    else:
        st.info("Önce ana CANO ekranında araştırma görevi ve kaynak okuma işlemini tamamlayın. Mevcut kayıtların üzerine yedek yüklenmez.")
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
        return generate_claim_quote_json(system, prompt, api_key=key)

if documents and key and st.button("İddiaları kaynak alıntılarıyla karşılaştır (1 model çağrısı)"):
    try:
        if owner:
            store = ColonySnapshotStore(os.environ["DATABASE_URL"])
            store.verify_schema()
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
    save_in_browser = st.checkbox(
        "Bu kişisel tarayıcıda CANO alıntı kayıtlarını yedeklemeyi onaylıyorum "
        "(şifrelenmemiş yerel depolama)",
        value=bool(st.session_state.get("cano_local_backup_opt_in")),
        key="cano_claim_backup_consent")
    if save_in_browser:
        try:
            payload = encode_browser_colony_backup(_snapshot(colony))
            receipt = browser_colony_component(write=payload)
            if browser_write_confirmed(receipt, payload):
                st.caption("Tarayıcı yedeği yazıldı ve geri okunarak doğrulandı.")
            else:
                st.info("Tarayıcı yedeği henüz doğrulanmadı; doğrulama mesajını kontrol edin.")
        except (ValueError, RuntimeError):
            st.warning("Tarayıcı yedeği başarısız; JSON yedeğini indirin.")
if not owner:
    st.download_button("Kaynak denetimini JSON yedekle",
                       data=json.dumps(_snapshot(colony), ensure_ascii=False, indent=2),
                       file_name="cano-claim-evidence.json", mime="application/json")

