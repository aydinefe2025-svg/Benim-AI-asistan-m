"""Explicitly operated Streamlit UI for persistent bounded agent colony."""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from core.agent_colony import AgentColony
from core.agent_review_loop import AgentReviewLoop
from core.collaborative_mission import CollaborativeMission
from core.scientific_sources import scientific_sources
from core.claim_evidence_comparison import compare_claim_to_sources
from core.colony_postgres import ColonySnapshotStore
from core.cano_command_center import _snapshot
from core.colony_restore import restore_colony_json_bytes, restore_owner_backup
from core.task_panel import _session_database_path


class AnswerAdapter:
    def __init__(self, answer):
        self.answer = answer

    def chat(self, model, system, prompt):
        return self.answer(system + "\n\n" + prompt)


def render_colony_panel(st, answer=None, *, owner_key=None, database_url=None):
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
        def _checkpoint(*, archive_prior=True):
            """CAS-verified owner backup after every explicitly run research stage."""
            if not (owner_key and database_url):
                return
            if (st.session_state.get("_cano_backup_owner_key") != owner_key
                    or "_cano_backup_expected" not in st.session_state):
                raise RuntimeError("Authenticated owner backup baseline is missing")
            current = _snapshot(colony)
            backup_store = ColonySnapshotStore(database_url)
            backup_store.verify_schema()
            backup_store.save_versioned_verified(
                owner_key, current,
                expected_prior=st.session_state["_cano_backup_expected"],
                archive_prior=archive_prior)
            st.session_state["_cano_backup_expected"] = current

        def _stage_checkpoint_callback():
            """One archived rollback boundary; each later stage is still read-back verified."""
            if not (owner_key and database_url):
                return None
            completed = [0]
            def save_stage():
                _checkpoint(archive_prior=(completed[0] == 0))
                completed[0] += 1
            return save_stage

        if not agents and owner_key and database_url:
            confirm_restore = st.checkbox(
                "Yedeğin yalnızca bu doğrulanmış hesaba ait olduğunu onaylıyorum; "
                "işlem yalnızca boş koloniye uygulanır.", value=False,
                key="colony_postgres_restore_confirm")
            if st.button("Kalıcı yedekten boş koloniyi geri yükle",
                         key="colony_postgres_restore"):
                if not confirm_restore:
                    st.warning("Geri yüklemek için önce açık onay verin.")
                else:
                    try:
                        count = restore_owner_backup(
                            colony, ColonySnapshotStore(database_url),
                            owner_key, approved=confirm_restore)
                        st.success(f"{count} uzman geri yüklendi ve SQLite kayıtları doğrulandı.")
                        st.rerun()
                    except LookupError:
                        st.warning("Bu hesap için kalıcı yedek bulunamadı.")
                    except (PermissionError, ValueError, RuntimeError,
                            OSError, sqlite3.Error):
                        st.error("Geri yükleme reddedildi; mevcut veriler korunuyor.")
                    except Exception:
                        st.error("Kalıcı yedeğe erişilemedi; mevcut veriler korunuyor.")
            if st.button("Eski PostgreSQL yedeklerini listele",
                         key="colony_show_archived_backups"):
                st.session_state["cano_show_archived_backups"] = True
            if st.session_state.get("cano_show_archived_backups"):
                try:
                    old_store = ColonySnapshotStore(database_url)
                    old_store.verify_schema()
                    versions = old_store.list_archived(owner_key)
                    if not versions:
                        st.info("Önceki yedek sürümü bulunamadı.")
                    else:
                        # Submitting clears the permission checkbox; no old
                        # confirmation can silently authorize a later restore.
                        with st.form("cano_archive_restore_form", clear_on_submit=True):
                            revision = st.selectbox(
                                "Geri yüklenecek eski yedek",
                                [item["revision"] for item in versions],
                                format_func=lambda value: "Yedek #" + str(value),
                                key="cano_archive_revision")
                            approved_archived = st.checkbox(
                                "Bu eski sürümü yalnızca boş kolonime geri yüklemeyi onaylıyorum",
                                value=False, key="cano_archive_confirm")
                            restore_archived = st.form_submit_button(
                                "Seçili eski yedeği geri yükle")
                        if restore_archived:
                            if not approved_archived:
                                st.warning("Eski yedeği geri yüklemek için yeni onay gerekli.")
                            else:
                                count = restore_owner_backup(
                                    colony, old_store, owner_key, approved=True,
                                    revision=revision)
                                st.success(f"Eski yedekten {count} uzman geri yüklendi.")
                                st.rerun()
                except LookupError:
                    st.warning("Seçili eski yedek artık bulunamıyor.")
                except (ValueError, RuntimeError, PermissionError,
                        OSError, sqlite3.Error):
                    st.error("Eski sürüm geri yükleme reddedildi; mevcut kayıtlar korunuyor.")
                except Exception:
                    st.error("Yedek geçmişine erişilemedi; kayıtlar değiştirilmedi.")
        if not agents:
            backup_upload = st.file_uploader(
                "Ajan kolonisini JSON yedekten geri yükle",
                type=["json"], key="colony_json_backup_upload")
            if st.button("Ajan yedeğini geri yükle", key="colony_json_backup_restore"):
                if backup_upload is None:
                    st.warning("Önce daha önce indirdiğiniz JSON yedeğini seçin.")
                elif backup_upload.size > 2_000_000:
                    st.error("Yedek 2 MB sınırını aşıyor; veri değiştirilmedi.")
                else:
                    try:
                        count = restore_colony_json_bytes(
                            colony, backup_upload.getvalue())
                        st.success(f"{count} ajan JSON yedekten geri yüklendi.")
                        st.rerun()
                    except (ValueError, RuntimeError, OSError, sqlite3.Error):
                        st.error("Yedek geçersiz veya mevcut kayıtlar dolu; veri değiştirilmedi.")
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

        st.caption("Kontrollü büyüme: eksik uzmanlıklar en fazla üçerli eklenir; "
                   "12 ajan kotası korunur. Bu, arka planda bağımsız çoğalma değildir.")
        if st.button("Koloniyi kontrollü büyüt (+3 uzman)", key="colony_grow"):
            try:
                created = colony.grow_specialists(approved=True, batch_size=3)
                if created:
                    st.success(f"{len(created)} yeni uzman kaydedildi.")
                    st.rerun()
                else:
                    st.info("Yeni uzmanlık kalmadı veya ajan kotası doldu.")
            except (RuntimeError, ValueError, PermissionError, sqlite3.Error):
                st.error("Kontrollü büyüme tamamlanamadı.")

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

        learning = colony.evaluate_learning(selected)
        st.caption(
            f"Öğrenme kaydı: {learning['accepted_lessons']} kabul edilmiş ders; "
            f"{learning['distinct_evidence']} farklı kanıt etiketi. "
            f"Kanıt çeşitliliği eşiği: {'sağlandı' if learning['retrieval_ready'] else 'henüz sağlanmadı'}. "
            "Bu, model ağırlıklarının eğitildiği veya kanıtların doğrulandığı anlamına gelmez."
        )
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
        if answer is not None and len(agents) >= 2:
            with st.form("colony_review_form"):
                reviewer = st.selectbox("Eleştiren uzman",
                                        [a["id"] for a in agents if a["id"] != selected],
                                        format_func=lambda k: labels[k])
                review_goal = st.text_area("Üç aşamalı inceleme görevi", max_chars=1200)
                review_run = st.form_submit_button("Taslak → eleştiri → düzeltme çalıştır")
            if review_run:
                try:
                    record = AgentReviewLoop(colony).execute(
                        selected, reviewer, review_goal,
                        client=AnswerAdapter(answer), model="configured-provider")
                    st.session_state["colony_last_review"] = record
                    st.success("Üç model çağrısı tamamlandı; inceleme kaydı oluşturuldu.")
                except (ValueError, RuntimeError, OSError, sqlite3.Error):
                    st.error("İnceleme döngüsü tamamlanamadı.")
        if st.session_state.get("colony_last_review"):
            review = st.session_state["colony_last_review"]
            for key, title in (("draft", "İlk taslak"),
                               ("critique", "Eleştiri"),
                               ("revision", "Düzeltilmiş taslak")):
                st.text_area(title, value=review[key], disabled=True,
                             height=130, key="review_" + key)
        if answer is not None and len(agents) >= 2:
            with st.form("colony_collaborative_mission_form"):
                mission_goal = st.text_area("Ortak araştırma görevi", max_chars=1200)
                crossref_opt_in = st.checkbox(
                    "Crossref DOI kaynak adaylarını da ara (görev metni dış servise gider; "
                    "tam belge doğrulanmaz)", value=False,
                    key="colony_crossref_opt_in")
                mission_run = st.form_submit_button("CANO ekibini birlikte çalıştır (4 aşama)")
            if mission_run:
                try:
                    # Refuse model charges when the owner backup is stale or unavailable.
                    _checkpoint()
                    mission = CollaborativeMission(colony).execute(
                        mission_goal, client=AnswerAdapter(answer),
                        model="configured-provider",
                        source_lookup=scientific_sources if crossref_opt_in else None,
                        on_checkpoint=_stage_checkpoint_callback())
                    # The fourth stage's completion status must also be durable.
                    _checkpoint(archive_prior=False)
                    st.session_state["colony_last_mission"] = mission
                    st.success("Dört aşamalı ekip görevi tamamlandı; bağımsız doğrulama bekliyor.")
                except (ValueError, RuntimeError, OSError, sqlite3.Error):
                    st.error("Ekip görevi durduruldu; PostgreSQL aşama yedeğini, ajanları "
                             "ve modeli kontrol edin. Doğrulanmamış kayıt tamamlandı sayılmaz.")
        if st.session_state.get("colony_last_mission"):
            mission = st.session_state["colony_last_mission"]
            st.caption("4 model çağrısı: plan, araştırma, eleştiri, sentez. "
                       "Bu sonuç bağımsız doğrulanmış bilgi değildir.")
            for stage in mission["stages"]:
                st.text_area("Ekip aşaması: " + stage["role"],
                             value=stage["output"], height=140, disabled=True,
                             key="mission_" + stage["role"])
                if stage["role"] == "planner" and "source_lookup_status" in stage:
                    status = stage["source_lookup_status"]
                    if status == "unavailable":
                        st.warning("Crossref metadata sorgusu başarısız; kaynak doğrulanmadı.")
                    elif status == "no_candidates":
                        st.info("Crossref'te güvenilir biçimde ayrıştırılabilen DOI adayı bulunamadı.")
                    else:
                        st.caption("Crossref bibliyografik DOI adayları — tam belge okunmadı, doğrulanmadı.")
                    for lead in stage.get("source_leads", []):
                        st.caption("Doğrulanmamış aday: " + lead["title"] + " — " + lead["url"])
            planner = next((stage for stage in mission["stages"] if stage["role"] == "planner"), {})
            source_documents = planner.get("source_documents", [])
            if planner.get("source_leads") and not source_documents:
                st.caption("Kaynak metni yalnızca bu düğmeye bastığında Europe PMC üzerinden aranır (en fazla iki DOI adayı).")
                if st.button("Açık erişimli kaynak pasajlarını oku", key="read_mission_sources_" + mission["id"]):
                    try:
                        manager = CollaborativeMission(colony)
                        manager.inspect_source_documents(mission["id"])
                        st.session_state["colony_last_mission"] = manager.get(mission["id"])
                        st.rerun()
                    except (ValueError, RuntimeError, OSError, sqlite3.Error):
                        st.error("Kaynak metni okunamadı; görev taslağı ve iddiası değişmedi.")
            elif source_documents:
                st.subheader("Kaynak pasajları ve iddia karşılaştırması")
                st.caption("Kaynak alıntısı tek başına doğrulama değildir. Karşılaştırma metin eşleşmesi tarar ve iddiayı review_pending durumunda bırakır.")
                for document in source_documents:
                    st.write("Kaynak:", document.get("title") or document.get("doi", ""))
                    st.write("URL:", document.get("url", ""))
                    st.caption("Kaynak okuma durumu: " + str(document.get("status", "unknown")))
                    excerpt = document.get("excerpt", "")
                    if excerpt:
                        st.text_area("Kaynak özeti", value=excerpt, height=120, disabled=True,
                                     key="mission_source_excerpt_" + mission["id"] + "_" + document.get("doi", "unknown"))
                comparable = [document for document in source_documents if document.get("excerpt")]
                if comparable:
                    claim_text = st.text_area(
                        "Karşılaştırılacak iddia (ekip taslağından seçip buraya yapıştır)",
                        max_chars=2000, key="mission_claim_compare_" + mission["id"])
                    selected_index = st.selectbox(
                        "Karşılaştırılacak kaynak pasajı", list(range(len(comparable))),
                        format_func=lambda index: comparable[index].get("title") or comparable[index].get("doi", "Kaynak"),
                        key="mission_claim_source_" + mission["id"])
                    if st.button("İddia ile pasajı karşılaştır", key="compare_mission_claim_" + mission["id"]):
                        try:
                            result = compare_claim_to_sources(claim_text, [{
                                "title": comparable[selected_index].get("title") or comparable[selected_index].get("doi", "Kaynak"),
                                "url": comparable[selected_index]["url"],
                                "content": comparable[selected_index]["excerpt"],
                            }])
                            labels = {
                                "possible_support": "Olası metin eşleşmesi",
                                "possible_contradiction": "Olası açık çelişki",
                                "insufficient_text_match": "Yeterli metin eşleşmesi yok",
                            }
                            st.info(labels[result["assessment"]])
                            for match in result["passages"]:
                                st.write(match["passage"])
                                st.caption("Eşleşen terimler: " + ", ".join(match["matched_terms"]) +
                                           " · örtüşme: " + f'{match["match_ratio"]:.0%}' +
                                           " · karşılaştırılan metin SHA-256: " + match["citation"]["compared_text_sha256"])
                            st.warning("Yalnızca sözcük örtüşmesi/açık olumsuzluk tarandı. Kaynağın özgünlüğü ve iddianın doğruluğu bağımsız inceleme bekliyor; durum review_pending kalır.")
                        except ValueError as exc:
                            st.error(str(exc))
                else:
                    st.info("Okunan kayıtlarda karşılaştırılabilir kaynak alıntısı yok.")
        if answer is not None and len(agents) >= 2:
            mission_manager = CollaborativeMission(colony)
            interrupted = mission_manager.interrupted()
            if interrupted:
                st.warning("Kesintiye uğrayan veya hâlâ çalışan ekip görevleri var.")
                for item in interrupted:
                    st.caption(item["status"] + ": " + item["task"][:160])
                    if item["status"] == "blocked":
                        if st.button("Görevi kaldığı yerden sürdür: " + item["id"][:8],
                                     key="resume_mission_" + item["id"]):
                            try:
                                _checkpoint()
                                result = mission_manager.resume(
                                    item["id"], client=AnswerAdapter(answer),
                                    model="configured-provider",
                                    on_checkpoint=_stage_checkpoint_callback())
                                _checkpoint(archive_prior=False)
                                st.session_state["colony_last_mission"] = result
                                st.success("Kayıtlı aşamalar korunarak görev sürdürüldü.")
                                st.rerun()
                            except (RuntimeError, ValueError, KeyError,
                                    OSError, sqlite3.Error):
                                st.error("Görev durduruldu; son doğrulanmış PostgreSQL "
                                         "aşama yedeği korunur, kayıtları kontrol edin.")
                if any(item["status"] == "running" for item in interrupted):
                    if st.button("1 saatten eski yarım görevleri kurtarmaya aç",
                                 key="recover_stale_colony_missions"):
                        recovered = mission_manager.recover_stale(
                            older_than_seconds=3600)
                        st.info(f"{len(recovered)} eski görev yeniden denemeye açıldı.")
                        st.rerun()
        with colony._db() as db:
            data = {"agents": [dict(row) for row in db.execute(
                "SELECT * FROM colony_agents ORDER BY created_at,id")],
                    "feedback": [dict(row) for row in db.execute(
                "SELECT * FROM colony_feedback ORDER BY id")]}
        with colony._db() as db:
            data["missions"] = [dict(row) for row in db.execute(
                "SELECT * FROM colony_missions ORDER BY created_at,id")] if db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='colony_missions'"
            ).fetchone() else []
        with colony._db() as db:
            data["reviews"] = [dict(row) for row in db.execute(
                "SELECT * FROM colony_reviews ORDER BY created_at,id")] if db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='colony_reviews'"
            ).fetchone() else []
        if owner_key and database_url:
            st.caption("PostgreSQL yedeği doğrulanmış kullanıcı hesabına bağlıdır.")
            if st.button("Ajan kayıtlarını kalıcı veritabanına yedekle",
                         key="colony_postgres_save"):
                # The cockpit previously read and bound the owner's exact
                # snapshot to this session. Refuse sidebar writes without
                # that provenance: otherwise a stale tab could bypass the
                # compare-and-swap protection in the main command center.
                if (st.session_state.get("_cano_backup_owner_key") != owner_key
                        or "_cano_backup_expected" not in st.session_state):
                    st.error("Hesap yedeği doğrulanamadı; eski sekmeden kayıt yazılmadı. "
                             "Oturumu yenileyip hesabınıza ait yedeği kontrol edin.")
                else:
                    try:
                        snapshot_store = ColonySnapshotStore(database_url)
                        snapshot_store.verify_schema()
                        snapshot_store.save_versioned_verified(
                            owner_key, data,
                            expected_prior=st.session_state["_cano_backup_expected"])
                        st.session_state["_cano_backup_expected"] = data
                        st.success("PostgreSQL yedeği hesap sürümüyle eşleşti; "
                                   "kaydedilip geri okundu.")
                    except Exception:
                        st.error("Hesabın yedeği değişmiş olabilir veya kayıt doğrulanamadı; "
                                 "eski kayıtların üzerine yazılmadı. JSON yedeği indirin.")
            if st.button("Kalıcı yedeği kontrol et", key="colony_postgres_check"):
                try:
                    saved = ColonySnapshotStore(database_url).load(owner_key)
                    if saved == data:
                        st.success("Yedek mevcut ve bu oturumun bütün kayıtlarıyla eşleşiyor.")
                    elif saved is None:
                        st.warning("Bu kullanıcı için kalıcı yedek bulunamadı.")
                    else:
                        st.warning("Yedek mevcut ama bu oturumun kayıtlarından farklı; güncel olduğu doğrulanmadı.")
                except Exception:
                    st.error("Kalıcı yedek okunamadı.")
        import json
        st.download_button("Ajanları ve dersleri JSON yedekle",
                           data=json.dumps(data, ensure_ascii=False, indent=2),
                           file_name="ajan-kolonisi-yedek.json",
                           mime="application/json", key="colony_backup")