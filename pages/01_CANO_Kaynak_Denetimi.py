"""CANO auditable source quote review, accessible via Streamlit Pages."""
import os
import json
import sqlite3
from pathlib import Path
import streamlit as st
from core.authentication import render_auth_gate
from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission
from core.task_panel import _session_database_path
from core.claim_evidence import audit_claim_quotes, record_source_claim_review
from core.groq_team import TeamRateLimitError
from core.groq_claim_json import generate_claim_quote_json
from core.cano_command_center import _snapshot
from core.colony_postgres import ColonySnapshotStore
from core.storage_config import cano_database_url
from core.cano_owner_checkpoint import save_owner_checkpoint, bind_restored_owner_baseline
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
                if st.session_state.get("_cano_backup_owner_key") not in (None, owner):
                    raise PermissionError("Session belongs to a different owner")
                store = ColonySnapshotStore(cano_database_url(os.environ))
                store.verify_schema()
                restore_result = restore_owner_backup(
                    colony, store, owner, approved=True,
                    archive_incomplete_missions=True)
                restored = restore_result["agent_count"]
                skipped = restore_result["archived_incomplete_missions"]
                bind_restored_owner_baseline(store, owner, st.session_state)
            except ValueError:
                st.warning(
                    "Eski CANO yedeğinde geri yükleme için gerekli alanlar eksik; "
                    "mevcut kayıtlar ve kalıcı yedek korunuyor.")
            except KeyError:
                st.warning("Yedek kaydının beklenen alanı eksik; mevcut kayıtlar ve kalıcı yedek korundu.")
            except LookupError:
                st.warning("Bu hesap için eşleşen kalıcı yedek bulunamadı; başka hesapların kayıtları açılmadı.")
            except PermissionError:
                st.warning("Kalıcı yedek erişim izni doğrulanamadı; hiçbir kayıt değiştirilmedi.")
            except RuntimeError:
                st.warning("Geri yükleme güvenli biçimde durdu; mevcut kayıtlar ve kalıcı yedek korundu.")
            except OSError:
                st.warning("Yerel oturum depolaması kullanılamadı; kalıcı yedek değiştirilmedi.")
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
            store = ColonySnapshotStore(cano_database_url(os.environ))
            store.verify_schema()
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony))
        audit_claim_quotes(manager, mid, client=Client(), model="configured-provider")
        if owner:
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony),
                                  archive_prior=False)
        st.rerun()
    except (ValueError, RuntimeError, TeamRateLimitError) as err:
        st.warning("Alıntı denetimi tamamlanamadı; önceki kayıtlar korunuyor.")
if not key:
    st.warning("Model bağlantısı yok; yeni iddia denetimi çalıştırılmadı.")
reviewed_mission = manager.get(mid)
for claim_index, item in enumerate(reviewed_mission["stages"][0].get("source_claim_audit", [])):
    docs = reviewed_mission["stages"][0].get("source_documents", [])
    source = next((doc for doc in docs
                   if isinstance(doc, dict)
                   and isinstance(doc.get("doi"), str)
                   and isinstance(item.get("doi"), str)
                   and doc["doi"].casefold() == item["doi"].casefold()), None)
    if item["status"] == "quote_found_unverified":
        st.success("Alıntı kaynakta bulundu; iddianın doğruluğu henüz incelenmedi.")
        st.caption(item["claim"] + " — " + item["doi"])
        st.code(item["quote"])
        st.link_button("Kaynağı aç", item["citation_url"])
    else:
        st.warning("Önerilen alıntı ilgili kaynakta bulunmadı.")
        st.caption(item["claim"])

    human_review = item.get("human_review")
    if human_review:
        label = ("İnsan tarafından birincil kaynağa göre desteklendi"
                 if human_review.get("supported")
                 else "İnsan incelemesinde desteklenmedi")
        st.info(label + ": " + human_review.get("rationale", ""))
    if not owner:
        st.caption("Karar kaydı yalnızca Google OIDC ile doğrulanmış hesapta kullanılabilir.")
        continue
    if not isinstance(source, dict) or source.get("status") not in {"full_text_excerpt", "abstract_excerpt"}:
        st.caption("Okunabilir kaynak yok; iddia için onay kaydedilemez.")
        continue
    if source.get("url"):
        st.link_button("İncelenecek kaynağı aç", source["url"])
    can_accept = (
        item.get("status") == "quote_found_unverified"
        and source.get("status") == "full_text_excerpt"
    )
    if not can_accept:
        st.caption("Kabul için eşleşen alıntı ve alınmış tam metin gerekir; bu kayıt yalnızca reddedilebilir.")
    with st.form(f"claim_source_review_{mid}_{claim_index}"):
        decision = st.radio(
            "Kaynak değerlendirmesi",
            ["Kaynak iddiayı destekliyor", "Kaynak iddiayı desteklemiyor"]
            if can_accept else ["Kaynak iddiayı desteklemiyor"],
            key=f"claim_decision_{mid}_{claim_index}")
        primary_confirmed = st.checkbox(
            "Tam metni inceleyip bunun birincil araştırma verisi olduğunu ve sonuçların iddiayı doğrudan desteklediğini doğruladım.",
            value=False, key=f"claim_primary_{mid}_{claim_index}",
            disabled=not can_accept)
        rationale = st.text_area(
            "İnceleme gerekçesi (en az 20 karakter)",
            max_chars=1000, key=f"claim_rationale_{mid}_{claim_index}")
        submitted_review = st.form_submit_button("İnsan incelemesini kaydet")
    if submitted_review:
        supported = decision == "Kaynak iddiayı destekliyor"
        try:
            store = ColonySnapshotStore(cano_database_url(os.environ))
            store.verify_schema()
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony))
            result = record_source_claim_review(
                manager, mid, claim_index, reviewer_id=owner,
                supported=supported, rationale=rationale,
                primary_source_confirmed=primary_confirmed)
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony),
                                  archive_prior=False)
        except (ValueError, PermissionError, RuntimeError, OSError, sqlite3.Error):
            st.warning("İnceleme kaydedilmedi; kaynak ve mevcut yedek korundu.")
        else:
            st.success("İnceleme denetim geçmişine ve hesap yedeğine kaydedildi.")
            st.rerun()
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

