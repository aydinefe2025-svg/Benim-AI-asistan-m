"""Visible CANO command center with explicitly controlled specialist missions.

The cockpit drives real SQLite-backed role calls and never claims independent
models, autonomous background processes, training or source verification.
"""
from __future__ import annotations

import json
import os
import sqlite3
from hashlib import sha256

from core.agent_colony import AgentColony
from core.collaborative_mission import CollaborativeMission
from core.colony_postgres import ColonySnapshotStore
from core.storage_config import database_provider_label
from core.browser_colony import (
    browser_colony_component, encode_browser_colony_backup,
    decode_browser_colony_backup, browser_write_confirmed,
)
from core.colony_restore import restore_empty_colony, restore_owner_backup
from core.cano_owner_checkpoint import bind_restored_owner_baseline
from core.authentication import auth_is_required
from core.groq_team import TeamRateLimitError
from core.cano_chat_tasks import stage_execution_notice
from core.scientific_sources import scientific_sources
from core.doi_priority import prioritize_requested_dois
from core.task_panel import _session_database_path
from core.cano_backup_bundle import create_portable_bundle, export_authorized_queue
from core.organism_lab_persistence import OrganismLabStore
from core.encrypted_backup_ui import render_encrypted_download


class _AnswerAdapter:
    def __init__(self, answer):
        self.answer = answer

    def chat(self, model, system, prompt):
        return self.answer(system + "\n\n" + prompt)


def prepare_cano_team(colony, *, approved=False):
    """Initialize a complete bounded role roster after an explicit button press."""
    if not approved:
        raise PermissionError("Team setup requires explicit approval")
    with colony._db() as db:
        total = db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]
    if not total:
        colony.create_founder(
            "research", "You are a careful Turkish research agent. Separate "
            "verified facts, hypotheses, and absent primary-source evidence.")
    # Two bounded, idempotent calls populate the six supported specialist roles.
    colony.grow_specialists(approved=True, batch_size=5)
    colony.grow_specialists(approved=True, batch_size=5)
    with colony._db() as db:
        return db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]


def read_cano_status(colony):
    """Read observed, session-local counts; never derive progress from marketing."""
    CollaborativeMission(colony)  # idempotent schema creation
    with colony._db() as db:
        agents = db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]
        roles = {row[0] for row in db.execute(
            "SELECT role FROM colony_agents WHERE state='active'")}
        lessons = db.execute(
            "SELECT COUNT(*) FROM colony_feedback WHERE accepted=1").fetchone()[0]
        missions = db.execute(
            "SELECT COUNT(*) FROM colony_missions").fetchone()[0]
        pending = db.execute(
            "SELECT COUNT(*) FROM colony_missions "
            "WHERE status='review_pending'").fetchone()[0]
        blocked = db.execute(
            "SELECT COUNT(*) FROM colony_missions "
            "WHERE status='blocked'").fetchone()[0]
        history = [dict(row) for row in db.execute(
            "SELECT id,task,status,created_at FROM colony_missions "
            "ORDER BY created_at DESC, rowid DESC LIMIT 12")]
    return {"agents": agents, "roles": roles, "lessons": lessons,
            "missions": missions, "review_pending": pending,
            "blocked": blocked, "history": history,
            "ready": "research" in roles and "evidence-reviewer" in roles}


def _snapshot(colony):
    """Downloadable manual backup from the same tables used by the side panel."""
    with colony._db() as db:
        result = {}
        for key, table in (("agents", "colony_agents"),
                           ("feedback", "colony_feedback"),
                           ("reviews", "colony_reviews"),
                           ("missions", "colony_missions")):
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,)).fetchone()
            result[key] = [dict(row) for row in db.execute("SELECT * FROM " + table)] if exists else []
    return result


def render_cano_command_center(st, answer=None, *, owner_key=None, database_url=None,
                               memories=None, research_tasks=None,
                               authorized_queue_store=None):
    """Render a top-level mission cockpit before the legacy sidebar/chat UI."""
    st.header("🚀 CANO Komuta Merkezi")
    st.caption("Uzmanları burada hazırla, gerçek ekip görevi çalıştır, "
               "aşamaları ve kaynak adaylarını incele. Sonuçlar inceleme bekleyen taslaklardır.")
    backup_store = None
    if owner_key is not None or database_url is not None:
        if (not isinstance(owner_key, str) or not owner_key.strip()
                or not database_url):
            st.error("CANO için doğrulanmış hesap ve PostgreSQL gereklidir.")
            return
        try:
            backup_store = ColonySnapshotStore(database_url)
            backup_store.verify_schema()
        except Exception:
            st.error("CANO PostgreSQL yedeği açılamadı; model çalıştırılmadı.")
            return
    base = os.environ.get("AGENT_COLONY_DB_PATH", "data/agent_colony.sqlite3")
    try:
        colony = AgentColony(_session_database_path(st, base), max_agents=12)
        manager = CollaborativeMission(colony)
        status = read_cano_status(colony)
    except (OSError, sqlite3.Error, ValueError):
        st.error("CANO ajan kayıtları açılamadı; görev çalıştırılmadı.")
        return

    # Bind the session to the authenticated owner and the snapshot it read.
    # Compare-and-swap is checked atomically inside PostgreSQL before writing.
    if backup_store is not None:
        previous_owner = st.session_state.get("_cano_backup_owner_key")
        if previous_owner and previous_owner != owner_key and status["agents"]:
            st.error("Bu oturumda hesap değişti; önceki hesabın CANO kayıtları başka hesaba aktarılmadı. Yeni oturum açın.")
            return
        if previous_owner != owner_key:
            st.session_state.pop("_cano_backup_expected", None)
            st.session_state["_cano_backup_owner_key"] = owner_key
        try:
            remote_snapshot = backup_store.load(owner_key)
        except Exception:
            st.error("Kalıcı CANO yedeği okunamadı; mevcut kayıtları korumak için yeni ekip oluşturulmadı.")
            return
        if remote_snapshot is not None and not isinstance(remote_snapshot, dict):
            st.error("Hesabın kalıcı CANO yedeği geçersiz; kayıtların üzerine yazılmadı.")
            return
        if status["agents"] == 0 and remote_snapshot is not None and any(
                remote_snapshot.get(name)
                for name in ("agents", "feedback", "reviews", "missions")):
            # Identity is verified, and the session-local destination is empty.
            # Restore only this owner's validated snapshot; never overwrite or
            # merge with a nonempty local colony.
            try:
                restored = restore_owner_backup(
                    colony, backup_store, owner_key, approved=True,
                    archive_incomplete_missions=True)
                bind_restored_owner_baseline(
                    backup_store, owner_key, st.session_state)
                status = read_cano_status(colony)
            except LookupError:
                st.warning("Bu hesap için kalıcı CANO yedeği bulunamadı.")
                return
            except (PermissionError, ValueError, RuntimeError,
                    OSError, sqlite3.Error):
                st.error("CANO yedeği doğrulanamadı; mevcut kayıtlar korunuyor.")
                return
            except Exception:
                st.error("CANO yedeğine güvenli biçimde erişilemedi; kayıtlar korunuyor.")
                return
            st.success(
                f"Bu doğrulanmış hesabın yedeğinden {restored['agent_count']} uzman "
                "boş oturuma geri yüklendi.")
            if restored["archived_incomplete_missions"]:
                st.warning(
                    f"{restored['archived_incomplete_missions']} eski eksik görev "
                    "çalışma kaydına alınmadı; özgün yedek sürüm geçmişinde korundu.")
            st.rerun()
            return
        if "_cano_backup_expected" not in st.session_state:
            if status["agents"] and remote_snapshot is not None:
                # Recovery deliberately converts interrupted "running" missions
                # to "blocked" before they can be explicitly resumed. This one
                # safe conversion must not be mistaken for an untrusted stale tab.
                archived_missions = remote_snapshot.get("missions", [])
                restored_shape = (
                    {**remote_snapshot, "missions": [
                        {**item, "status": "blocked"}
                        if isinstance(item, dict) and item.get("status") == "running"
                        else item for item in archived_missions]}
                    if isinstance(archived_missions, list) else None
                )
                if restored_shape != _snapshot(colony):
                    st.error("Bu oturumun CANO kayıtları hesaptaki güncel yedekle uyuşmuyor; "
                             "yeni görev başlatılmadı. Önce mevcut oturumu yedekleyin.")
                    return
            st.session_state["_cano_backup_expected"] = remote_snapshot

    # Streamlit rejects changing a widget's key after that widget has rendered.
    # Apply pending updates from restore/clear at the START of the next rerun.
    if st.session_state.pop("_cano_backup_enable_next_run", False):
        st.session_state["cano_local_backup_opt_in"] = True
    elif st.session_state.pop("_cano_backup_disable_next_run", False):
        st.session_state["cano_local_backup_opt_in"] = False

    # Never reuse shared-browser storage between authenticated accounts.
    # Signed-in users must use authenticated owner-scoped PostgreSQL storage.
    browser_backup_enabled = not auth_is_required(os.environ)
    local_opt_in = (st.checkbox(
        "Bu tarayıcıda CANO ekibini ve araştırma kayıtlarını otomatik yedekle "
        "(yalnızca kişisel cihazda; tarayıcı depolaması şifrelenmemiştir)",
        value=False, key="cano_local_backup_opt_in")
        if browser_backup_enabled else False)
    clear_local = (st.button(
        "Bu tarayıcıdaki CANO yedeğini sil",
        key="cano_local_backup_clear")
        if browser_backup_enabled else False)
    if clear_local:
        st.session_state["_cano_backup_disable_next_run"] = True
        local_opt_in = False

    write = None
    if local_opt_in and status["agents"] and not clear_local:
        try:
            write = encode_browser_colony_backup(_snapshot(colony))
        except (ValueError, TypeError):
            st.warning("Yerel yedek kapasitesi aşıldı; bu kaydı JSON olarak dışa aktarın.")
    report = (browser_colony_component(write=write, clear=clear_local)
              if browser_backup_enabled else None)
    if isinstance(report, dict) and report.get("status") == "error":
        st.warning("Tarayıcı yedeğine erişilemiyor; kayıtlar yalnızca bu oturumda.")
    elif clear_local and isinstance(report, dict) and report.get("ack") == "cleared":
        st.caption("Bu tarayıcıdaki CANO yedeği silindi.")
    elif (not clear_local and status["agents"] == 0
          and isinstance(report, dict) and report.get("payload")):
        try:
            recovered = decode_browser_colony_backup(report)
            count = restore_empty_colony(colony, recovered)
        except (ValueError, RuntimeError, OSError, sqlite3.Error):
            st.warning("Tarayıcı yedeği doğrulanamadı; mevcut kayıtlar değiştirilmedi.")
        else:
            st.session_state["_cano_backup_enable_next_run"] = True
            st.success(f"Bu tarayıcının önceki CANO yedeğinden {count} uzman geri yüklendi.")
            st.rerun()
            return
    if local_opt_in and write is not None:
        if browser_write_confirmed(report, write):
            st.caption("Tarayıcı yedeği yazılıp geri okunarak doğrulandı. "
                       "Bu bir hesaplar arası veya sunucu PostgreSQL yedeği değildir.")
        else:
            st.caption("Tarayıcı yedeği henüz doğrulanmadı; sayfadan ayrılmadan "
                       "önce yedek onayının görünmesini kontrol edin.")

    def _checkpoint(*, archive_prior=True):
        if backup_store is not None:
            snapshot = _snapshot(colony)
            backup_store.save_versioned_verified(
                owner_key, snapshot,
                expected_prior=st.session_state["_cano_backup_expected"],
                archive_prior=archive_prior)
            st.session_state["_cano_backup_expected"] = snapshot

    # Expose only observed counters to the capability/status chat route.
    # Task text and source evidence remain confined to their dedicated views.
    st.session_state["_cano_runtime_status"] = {
        key: status[key]
        for key in ("agents", "missions", "review_pending", "lessons", "blocked")
    }

    cols = st.columns(4)
    for col, label, value in zip(
        cols, ("Uzman", "Ekip görevleri", "İnceleme bekleyen", "Kabul edilmiş ders"),
        (status["agents"], status["missions"],
         status["review_pending"], status["lessons"])):
        col.metric(label, value)

    if backup_store is None:
        st.caption("Bu oturumda yalnızca geçici SQLite var; JSON yedeği alın.")
    else:
        st.caption("Açıkça başlatılan görevlerin sonuçları hesap sahibine ait PostgreSQL "
                   "sürümlü yedeğine otomatik yazılır. Ani sunucu kapanmalarında "
                   "tam aşama garantisi yoktur; Komuta Merkezi'nden şifreli dış yedek alın.")
        st.caption(f"CANO yedek veritabanı sağlayıcısı: {database_provider_label(database_url)}.")
    st.caption("Uzmanlıklar rol bazlı model çağrılarıdır, ayrı eğitilmiş modeller değildir.")
    if st.button("🚀 CANO ekibini hazırla (1 kurucu + 6 uzman)",
                 key="cano_prepare_team"):
        try:
            count = prepare_cano_team(colony, approved=True)
            _checkpoint()
            st.success(f"{count} rol kaydı hazır; ekip görevine geçebilirsiniz.")
            st.rerun()
            return
        except (ValueError, PermissionError, RuntimeError, sqlite3.Error):
            st.error("Ekip veya kalıcı yedek doğrulanamadı; yerel veri silinmedi.")
            return

    if not status["ready"]:
        st.info("Ekip görevi için kurucu araştırmacı ve kanıt inceleyici gerekiyor. "
                "Yukarıdaki hazırlama düğmesini kullanın.")
    elif answer is None:
        st.warning("Model bağlantısı olmadan ekip görevi çalıştırılamaz.")
    else:
        st.caption("Bir görev dört sıralı model çağrısı yapar; yalnızca açıkça "
                   "başlattığınızda çalışır. Ek maliyet sağlayıcı kotanıza bağlıdır.")
        st.caption("Yazılım görevlerinde yalnızca izin listesindeki sınırlı kaynak kodu "
                   "seçili sağlayıcıya inceleme bağlamı olarak gönderilir; kod çalıştırılmaz.")
        with st.form("cano_cockpit_mission_form"):
            goal = st.text_area(
                "CANO'ya ekip görevi ver", max_chars=1200,
                placeholder="Örnek: Güneş enerjisinin iki avantajını ve bir sınırlamasını "
                            "kanıt eksikleriyle birlikte araştır.",
                key="cano_cockpit_goal")
            lookup = st.checkbox(
                "Bilimsel DOI kaynak adaylarını Crossref'te ara "
                "(görev metni dış servise iletilir)", value=False,
                key="cano_cockpit_crossref")
            submitted = st.form_submit_button("🧠 Ekibi çalıştır — 4 aşama")
        if submitted:
            if not isinstance(goal, str) or not goal.strip():
                st.warning("Önce araştırma görevini yazın.")
            else:
                # Check durable write access before an expensive model request.
                try:
                    _checkpoint()
                except Exception:
                    st.error("PostgreSQL yedeği hazır değil; model çağrısı yapılmadı.")
                    return
                # Preserve one rollback boundary for the mission, not an
                # extra archived revision for each of its four model stages.
                # Every stage still gets a CAS-verified current PG snapshot.
                stage_checkpoint_count = [0]
                def _durable_stage_checkpoint():
                    _checkpoint(archive_prior=(stage_checkpoint_count[0] == 0))
                    stage_checkpoint_count[0] += 1
                try:
                    def _lookup_sources(_query, limit=3):
                        candidates = (scientific_sources(_query, limit=limit)
                                      if lookup else [])
                        return prioritize_requested_dois(goal, candidates, limit=limit)

                    result = manager.execute(
                        goal, client=_AnswerAdapter(answer),
                        model="configured-provider",
                        source_lookup=(_lookup_sources
                                       if lookup or prioritize_requested_dois(
                                           goal, [], limit=1)
                                       else None),
                        on_checkpoint=_durable_stage_checkpoint if backup_store is not None else None)
                except TeamRateLimitError:
                    try:
                        _checkpoint(archive_prior=(stage_checkpoint_count[0] == 0))
                    except Exception:
                        st.error("Kısmi görev PostgreSQL'e kaydedilemedi; JSON yedeği alın.")
                    st.warning("Groq kotası doldu. Kısmi aşamalar yerel SQLite'da korundu; "
                               "kota yenilendiğinde kaldığınız yerden sürdürün.")
                except (RuntimeError, ValueError, OSError, sqlite3.Error):
                    try:
                        _checkpoint(archive_prior=(stage_checkpoint_count[0] == 0))
                    except Exception:
                        st.error("Kısmi görev PostgreSQL'e kaydedilemedi; JSON yedeği alın.")
                    st.error("Görev tamamlanamadı; yerel kayıt ve kısmi aşamalar korundu.")
                else:
                    try:
                        _checkpoint(archive_prior=False)
                    except Exception:
                        st.error("Görev yerelde tamamlandı ama PostgreSQL yedeği "
                                 "doğrulanamadı; JSON yedeği alın.")
                        return
                    st.session_state["cano_cockpit_latest_mission"] = result["id"]
                    st.rerun()
                    return

    if status["blocked"]:
        st.warning(f"{status['blocked']} yarım kalmış görev kayıtlı. "
                   "Kayıtlı aşamalar korunuyor; aşağıdan kaldığınız yerden sürdürebilirsiniz.")
        for item in manager.interrupted(limit=10):
            if item["status"] != "blocked":
                continue
            saved = manager.get(item["id"])
            completed = len(saved["stages"])
            st.caption(f"{item['task'][:160]} — {completed}/4 aşama kayıtlı")
            if st.button("↻ Görevi kaldığı yerden sürdür: " + item["id"][:8],
                         key="cano_resume_partial_" + item["id"]):
                try:
                    _checkpoint()
                except Exception:
                    st.error("Kalıcı CANO yedek kontrolü geçmedi; görev sürdürülmedi. "
                             "Bu denemede sağlayıcı çağrısı yapılmadı; kayıtlı aşamalar korundu.")
                    return
                checkpoint_count = [0]
                    def _resume_checkpoint():
                        _checkpoint(archive_prior=(checkpoint_count[0] == 0))
                        checkpoint_count[0] += 1
                    result = manager.resume(
                        item["id"], client=_AnswerAdapter(answer),
                        model="configured-provider",
                        on_checkpoint=_resume_checkpoint if backup_store is not None else None)
                    _checkpoint(archive_prior=False)
                    st.session_state["cano_cockpit_latest_mission"] = result["id"]
                    st.success("Kayıtlı aşamalar korundu; görev kaldığı yerden tamamlandı.")
                    st.rerun()
                    return
                except (RuntimeError, ValueError, KeyError, OSError, sqlite3.Error) as exc:
                    # Lazy import avoids the module cycle: colony_panel imports _snapshot here.
                    from core.colony_panel import mission_failure_message
                    st.error(mission_failure_message(
                        exc, getattr(manager, "last_failure", None)))

    # Refresh after a button-triggered task so results are visible on this run.
    status = read_cano_status(colony)
    latest_id = st.session_state.get("cano_cockpit_latest_mission")
    if not latest_id and status["history"]:
        latest_id = status["history"][0]["id"]
    if latest_id:
        try:
            latest = manager.get(latest_id)
        except (KeyError, ValueError, sqlite3.Error):
            st.warning("Önceki görev bu geçici oturumda bulunamadı; "
                       "varsa indirilmiş yedeği geri yükleyin.")
        else:
            st.subheader("🧩 Son gerçek ekip görevi")
            st.caption("Görev: " + latest["task"])
            st.caption("Durum: " + latest["status"] +
                       " — 'review_pending' bağımsız doğrulama yapıldığı anlamına gelmez.")
            names = {"planner": "1 · Planlama", "researcher": "2 · Araştırma",
                     "reviewer": "3 · Eleştirel inceleme",
                     "synthesis": "4 · Düzeltilmiş sonuç"}
            for stage in latest["stages"]:
                with st.expander(names.get(stage["role"], stage["role"]),
                                 expanded=(stage["role"] == "synthesis")):
                    legacy_notice = stage_execution_notice(stage)
                    if legacy_notice:
                        st.warning(legacy_notice)
                    st.caption("Bu aşama model metnidir; kod, cihaz veya fiziksel deney "
                               "çalıştırılmadı. Gerçek kaynak okuma kayıtları ayrıca gösterilir.")
                    st.markdown(stage["output"])
                    lessons_used = stage.get("approved_lessons_used")
                    if type(lessons_used) is int and lessons_used >= 0:
                        st.caption(
                            f"Bu aşamaya eklenen kabul edilmiş ders sayısı: {lessons_used}. "
                            "Bu sayı, dersin sonucu iyileştirdiğini kanıtlamaz.")
                    if stage["role"] == "planner" and "source_lookup_status" in stage:
                        st.caption("DOI adayları: " + stage["source_lookup_status"] +
                                   ". Yalnızca bibliyografik metadata; tam metin doğrulanmadı.")
                        for lead in stage.get("source_leads", []):
                            st.link_button("DOI adayı: " + lead["title"][:90],
                                           lead["url"])

    if latest_id:
        try:
            inspected = manager.get(latest_id)
        except (KeyError, ValueError, sqlite3.Error):
            inspected = None
        if inspected and inspected["status"] == "review_pending" and inspected["stages"]:
            planner_stage = inspected["stages"][0]
            if planner_stage.get("source_leads"):
                with st.expander("📑 Gerçek kaynak metnini incele", expanded=False):
                    st.caption("Açık seçimle Europe PMC'den en fazla iki açık erişim "
                               "makalesi veya özet metni okunur; sorgu DOI numarasıdır. "
                               "Belge alıntısı bir iddianın doğrulandığı anlamına gelmez.")
                    if st.button("Kaynak belgelerini oku ve göreve kaydet",
                                 key="cano_read_sources_" + latest_id):
                        try:
                            manager.inspect_source_documents(latest_id)
                            _checkpoint()
                            st.rerun()
                            return
                        except (RuntimeError, ValueError, OSError, sqlite3.Error):
                            st.error("Kaynak okuma başarısız; görev taslağı korunuyor.")
                    if planner_stage.get("source_documents") and any(
                            isinstance(doc, dict) and doc.get("status") in (
                                "not_found", "unavailable", "metadata_only")
                            for doc in planner_stage["source_documents"]):
                        if st.button("Eksik DOI kaynaklarını yeniden oku",
                                     key="cano_retry_sources_" + latest_id):
                            try:
                                manager.inspect_source_documents(
                                    latest_id, refresh_missing=True)
                                _checkpoint()
                                st.rerun()
                                return
                            except (RuntimeError, ValueError, OSError, sqlite3.Error):
                                st.error("Eksik kaynak tekrar okunamadı; önceki kanıtlar korundu.")
                    for doc in planner_stage.get("source_documents", []):
                        st.caption(doc.get("title", "Kaynak") + ": " +
                                   doc.get("status", "unavailable") +
                                   " — iddia doğrulama yapılmadı.")
                        st.link_button("Kaynağı aç", doc["url"])
                        if doc.get("excerpt"):
                            st.caption("Belgeden kısa metin: " + doc["excerpt"])

    if status["history"]:
        st.caption("Bu oturumda kayıtlı son ekip görevleri: " +
                   " · ".join(x["task"][:45] + " (" + x["status"] + ")"
                              for x in status["history"][:5]))
    if status["agents"] or owner_key:
        snapshot = _snapshot(colony)
        if owner_key:
            secure_key = "_cano_secure_export_" + sha256(
                owner_key.encode("utf-8")).hexdigest()[:16]
            previous_secure_key = st.session_state.get("_cano_secure_export_owner")
            if previous_secure_key and previous_secure_key != secure_key:
                for suffix in ("_encrypted", "_source_digest", "_error",
                               "_passphrase", "_confirm", "_download"):
                    st.session_state.pop(previous_secure_key + suffix, None)
            st.session_state["_cano_secure_export_owner"] = secure_key
            if (memories is None or research_tasks is None
                    or authorized_queue_store is None or not database_url):
                st.error("Şifreli tam yedek hazır değil: hesap hafızası, araştırma görevi "
                         "onaylı kuyruk veya laboratuvar veritabanına erişim yok. "
                         "Eksik paketi indirmedim.")
            else:
                try:
                    jobs = export_authorized_queue(authorized_queue_store)
                    lab_records = OrganismLabStore(
                        owner_key, database_url).export_for_backup()
                    portable = create_portable_bundle(
                        colony=snapshot, memories=memories,
                        research_tasks=research_tasks,
                        authorized_queue=jobs,
                        organism_records=lab_records,
                    )
                except Exception:
                    st.error("Şifreli CANO paketi oluşturulamadı; veri değiştirilmedi.")
                else:
                    render_encrypted_download(
                        st, label="💾 Şifreli CANO hesap yedeğini indir",
                        filename="cano-hesap-yedegi.canoenc",
                        plaintext=portable, storage_key=secure_key)
                    st.caption("Paket: ajanlar, ekip görevleri, dersler, hafıza, "
                               "araştırma görev/taslakları ve onaylı kuyruk kayıtları. "
                               "Her bölümün kullanılabilirlik durumu manifestte yer alır.")
        elif status["agents"]:
            payload = json.dumps(snapshot, ensure_ascii=False, indent=2)
            st.download_button(
                "💾 CANO ajanlarını, görevlerini ve dersleri JSON yedekle",
                data=payload, file_name="cano-ekip-yedegi.json",
                mime="application/json", key="cano_cockpit_backup")
            st.caption("Geri yükleme: yan menü → Öğrenen uzman ajanlar → "
                       "JSON yedekten geri yükle (yalnızca boş oturum).")

