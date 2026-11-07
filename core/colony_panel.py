"""Explicitly operated Streamlit UI for persistent bounded agent colony."""
from __future__ import annotations

import os
import json
import sqlite3
from pathlib import Path

from core.agent_colony import AgentColony
from core.agent_review_loop import AgentReviewLoop
from core.cano_autonomous_improvement import run_bounded_improvement_cycle
from core.collaborative_mission import CollaborativeMission
from core.scientific_sources import scientific_sources
from core.claim_evidence_comparison import compare_claim_to_sources
from core.benchmark_harness import parse_memory_benchmark_cases, run_colony_memory_benchmark
from core.colony_postgres import ColonySnapshotStore
from core.cano_command_center import _snapshot
from core.colony_restore import restore_colony_json_bytes, restore_owner_backup
from core.task_panel import _session_database_path


def snapshots_match(left, right):
    """Compare table snapshots without treating row order as data."""
    def canonical(value):
        if isinstance(value, dict):
            return {key: canonical(item) for key, item in value.items()}
        if isinstance(value, list):
            rows = [canonical(item) for item in value]
            if all(isinstance(item, dict) for item in rows):
                rows.sort(key=lambda item: json.dumps(
                    item, sort_keys=True, ensure_ascii=False, separators=(",", ":")))
            return rows
        return value

    return json.dumps(canonical(left), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":")) == json.dumps(
        canonical(right), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class AnswerAdapter:
    def __init__(self, answer):
        self.answer = answer

    def chat(self, model, system, prompt):
        return self.answer(system + "\n\n" + prompt)


def mission_failure_message(exc, failure=None):
    """Show failure location without exposing raw provider/database exception text."""
    failure = failure if isinstance(failure, dict) else {}
    phase_labels = {
        "mission_setup": "görev hazırlığı",
        "model_call": "model sağlayıcı çağrısı",
        "sqlite_stage_write": "yerel aşama kaydı",
        "owner_backup_checkpoint": "hesap PostgreSQL yedek kontrolü",
        "completion_write": "görev tamamlama kaydı",
    }
    phase = phase_labels.get(failure.get("phase"), "başlangıç/ön kontrol")
    role = failure.get("role")
    role_text = f", {role} rolü" if isinstance(role, str) and role else ""
    error_type = failure.get("exception_type")
    if not isinstance(error_type, str) or not error_type:
        error_type = type(exc).__name__[:80]
    return (f"Görev durdu: {phase}{role_text} başarısız oldu "
            f"(hata türü: {error_type}). Görev tamamlanmadı; kaydedilmiş aşamalar korundu. "
            "Hassas olabilecek hata metni güvenlik için gösterilmedi.")


def render_colony_panel(st, answer=None, *, owner_key=None, database_url=None):
    expand_restore = bool(st.session_state.pop("_cano_restore_panel_open_requested", False))
    with st.sidebar.expander("🧬 Öğrenen uzman ajanlar", expanded=expand_restore):
        description = (
            "Ajanlar yapılandırılmış uzman örnekleridir; kendi kendine çalışan süreçler "
            "veya eğitilmiş yeni modeller değildir. İşlemler yalnızca düğmeye basınca çalışır.")
        if owner_key and database_url:
            st.caption(
                description + " Koloni değişiklikleri oturum SQLite'ında işlenir ve "
                "hesaba bağlı PostgreSQL yedeğine CAS doğrulamasıyla kaydedilir.")
        else:
            st.caption(
                description + " Kayıtlar oturuma özel geçici SQLite dosyasındadır; "
                "JSON yedeği alın.")
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
            expected = st.session_state["_cano_backup_expected"]
            if (not current["agents"] and isinstance(expected, dict)
                    and any(expected.get(name)
                            for name in ("agents", "feedback", "reviews", "missions"))):
                # A missing local database must not erase an existing owner's
                # complete remote research archive. Restore it first.
                raise RuntimeError("Empty local colony cannot replace an existing owner backup")
            backup_store = ColonySnapshotStore(database_url)
            backup_store.verify_schema()
            backup_store.save_versioned_verified(
                owner_key, current,
                expected_prior=st.session_state["_cano_backup_expected"],
                archive_prior=archive_prior)
            st.session_state["_cano_backup_expected"] = current

        def _persist_mutation(mutate):
            # Refuse stale owner writes before changing the local colony.
            try:
                _checkpoint()
            except Exception:
                st.error("Kalıcı hesap yedeği doğrulanamadı; kayıt değiştirilmedi.")
                return False, None
            result = mutate()
            try:
                _checkpoint(archive_prior=False)
            except Exception:
                st.error("Değişiklik yerel oturumda korundu ama PostgreSQL yedeği "
                         "doğrulanamadı; JSON yedeği alın.")
                return False, result
            return True, result

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
                        owner_store = ColonySnapshotStore(database_url)
                        count = restore_owner_backup(
                            colony, owner_store, owner_key, approved=confirm_restore)
                        # The next checkpoint must compare against this exact
                        # authenticated remote readback, not an old empty baseline.
                        st.session_state["_cano_backup_owner_key"] = owner_key
                        st.session_state["_cano_backup_expected"] = owner_store.load(owner_key)
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
                                # Archived revisions are promoted to current by
                                # restore_owner_backup. Bind this session to the
                                # verified readback so the next checkpoint can
                                # continue from the selected historical state.
                                st.session_state["_cano_backup_owner_key"] = owner_key
                                st.session_state["_cano_backup_expected"] = old_store.load(owner_key)
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
                        saved, count = _persist_mutation(
                            lambda: restore_colony_json_bytes(
                                colony, backup_upload.getvalue()))
                        if saved:
                            st.success(f"{count} ajan JSON yedekten geri yüklendi." +
                                       (" Hesap yedeği doğrulandı." if owner_key and database_url
                                        else " Kalıcı kayıt için JSON yedeğini saklayın."))
                            st.rerun()
                    except Exception:
                        st.error("JSON geri yükleme veya PostgreSQL yedeği doğrulanamadı; "
                                 "yerel veriler değişmiş olabilir, JSON yedeğinizi koruyun.")
            if st.button("Kurucu araştırma ajanını oluştur", key="colony_founder"):
                try:
                    saved, _ = _persist_mutation(lambda: colony.create_founder(
                        "research", "You are a careful Turkish research agent. "
                        "Separate verified facts from assumptions and draft claims."))
                    if saved:
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
                saved, child = _persist_mutation(
                    lambda: colony.spawn(selected, role, instructions, approved=True))
                if not saved:
                    return
                st.success("Uzman ajan kaydedildi: " + child[:8])
                st.rerun()
            except (ValueError, RuntimeError, PermissionError, sqlite3.Error):
                st.warning("Ajan oluşturulamadı; kota veya alanları kontrol edin.")

        st.caption("Kontrollü büyüme: eksik uzmanlıklar en fazla üçerli eklenir; "
                   "12 ajan kotası korunur. Bu, arka planda bağımsız çoğalma değildir.")
        if st.button("Koloniyi kontrollü büyüt (+3 uzman)", key="colony_grow"):
            try:
                saved, created = _persist_mutation(
                    lambda: colony.grow_specialists(approved=True, batch_size=3))
                if not saved:
                    return
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
                saved, _ = _persist_mutation(
                    lambda: colony.feedback(selected, task, lesson, evidence, accepted=accepted))
                if not saved:
                    return
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
        if answer is not None and not learning["accepted_lessons"]:
            st.info(
                "Ders etkisini ölçmek için önce bu uzmanda en az bir dersi "
                "kabul edip kaydedin; ardından kapalı/açık karşılaştırma burada görünür."
            )
        if answer is not None and learning["accepted_lessons"]:
            with st.expander("📊 Kabul edilmiş derslerin etkisini ölç", expanded=False):
                st.caption(
                    "Aynı insan etiketli testleri önce dersler kapalı, sonra açık çalıştırır. "
                    "Beş vakaya kadar; her vaka için dört sağlayıcı çağrısı (en fazla 20). "
                    "Sağlayıcı kotanızdan ücret/kota tüketebilir. Yalnız bu düğmeye bastığınızda çalışır. "
                    "Tam yanıt eşleşmesi ölçülür; genel doğruluk veya bilimsel geçerlilik değildir."
                )
                with st.form("colony_memory_benchmark_form"):
                    dataset_ref = st.text_input(
                        "Test takımı etiketi/sürümü (yalnız kayıt etiketi)", max_chars=120)
                    cases_json = st.text_area(
                        "İnsan tarafından etiketlenmiş testler (JSON)", max_chars=12_000,
                        placeholder='[{"case_id":"vaka-1","prompt":"...","expected":"..."}]')
                    benchmark_run = st.form_submit_button(
                        "Ders açık/kapalı karşılaştırmasını başlat")
                if benchmark_run:
                    try:
                        cases = parse_memory_benchmark_cases(cases_json)
                        if not isinstance(dataset_ref, str) or not dataset_ref.strip():
                            raise ValueError("Test takımı etiketi/sürümü gerekli")
                        # Persist and read back the current accepted lessons before
                        # making the explicitly requested provider calls.
                        _checkpoint(archive_prior=False)
                        measured = run_colony_memory_benchmark(
                            colony, selected, cases, client=AnswerAdapter(answer),
                            model="configured-provider",
                            source_refs=(dataset_ref.strip(),), safety_pass=False)
                        st.session_state["cano_memory_benchmark"] = {
                            "agent_id": selected,
                            "dataset_ref": dataset_ref.strip(),
                            "result": measured,
                        }
                    except (ValueError, RuntimeError, PermissionError, OSError,
                            sqlite3.Error) as exc:
                        st.warning("Karşılaştırma başlatılamadı; sağlayıcı veya test alanlarını kontrol edin.")
                benchmark = st.session_state.get("cano_memory_benchmark")
                if benchmark and benchmark.get("agent_id") == selected:
                    measured = benchmark["result"]
                    baseline = measured["baseline"]
                    candidate = measured["candidate"]
                    st.write(
                        f"Dersler kapalı: {baseline.passed}/{baseline.total} "
                        f"({baseline.score:.0%}); açık: {candidate.passed}/{candidate.total} "
                        f"({candidate.score:.0%}); fark: {measured['delta']:+.0%}."
                    )
                    st.caption(
                        "Tekrar tutarlılığı — kapalı: "
                        f"{measured['reproducible']['baseline']}; açık: "
                        f"{measured['reproducible']['candidate']}. "
                        f"Geriye giden vakalar: {len(measured['regressed_case_ids'])}. "
                        "Bu küçük test seti CANO'nun genel performansını kanıtlamaz; "
                        "dersler otomatik etkinleştirilmez. Sonuç bu oturumda tutulur."
                    )
                    safe_report = {
                        "agent_id": selected,
                        "dataset_ref": benchmark["dataset_ref"],
                        "baseline_passed": baseline.passed,
                        "candidate_passed": candidate.passed,
                        "total_cases": baseline.total,
                        "delta": measured["delta"],
                        "reproducible": measured["reproducible"],
                        "regressed_case_ids": measured["regressed_case_ids"],
                        "improved_case_ids": measured["improved_case_ids"],
                        "case_results": measured["case_results"],
                        "benchmark_sha256": measured["benchmark_sha256"],
                        "comparison": measured["comparison"],
                        "model_weights_updated": False,
                        "safety_pass": False,
                    }
                    st.download_button(
                        "Ölçüm raporunu indir (istemler/yanıtlar içermez)",
                        data=json.dumps(safe_report, ensure_ascii=False, indent=2),
                        file_name="cano-ders-etki-olcumu.json",
                        mime="application/json", key="cano_memory_benchmark_download")
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
            st.caption(
                "Sınırlı CANO gelişim döngüsü: 4 inceleme/aday çağrısı + en fazla "
                "20 kıyas çağrısı. Sağlayıcı kotası veya ücret doğabilir; yalnızca "
                "aşağıdaki onay kutusu ve düğmeyle çalışır. Aday kazansa bile belleğe "
                "eklenmesi için ayrıca sen onay verirsin.")
            with st.form("colony_review_form"):
                reviewer = st.selectbox("Eleştiren uzman",
                                        [a["id"] for a in agents if a["id"] != selected],
                                        format_func=lambda k: labels[k])
                review_goal = st.text_area(
                    "Geliştirme görevi", max_chars=1200)
                run_improvement = st.checkbox(
                    "Bir ders adayı üretip beş sabit testte sınamayı onaylıyorum "
                    "(en fazla 24 model çağrısı)",
                    value=False, key="cano_bounded_improvement_opt_in")
                dataset_ref = st.text_input(
                    "Beş insan etiketli test için sürüm/etiket", max_chars=120)
                cases_json = st.text_area(
                    "Beş sabit test (JSON; case_id, prompt, expected)",
                    max_chars=12000,
                    placeholder='[{"case_id":"test-1","prompt":"...","expected":"..."}]')
                review_run = st.form_submit_button(
                    "CANO incelemesini ve sınırlı döngüyü çalıştır")
            if review_run:
                try:
                    if run_improvement:
                        saved, result = _persist_mutation(lambda:
                            run_bounded_improvement_cycle(
                                colony, selected, reviewer, review_goal, cases_json,
                                dataset_ref, client=AnswerAdapter(answer),
                                model="configured-provider"))
                        if not saved:
                            return
                        st.session_state["cano_improvement_cycle"] = result
                        st.session_state["colony_last_review"] = AgentReviewLoop(colony).get(
                            result["review_id"])
                        if result["status"] == "review_pending":
                            st.success(
                                "Aday beş testte iyileşme gösterdi; yalnızca inceleme "
                                "bekleyen ders olarak kaydedildi.")
                        elif result["status"] == "blocked":
                            st.warning(
                                "Döngü tamamlanamadı; biten inceleme arşivlendi, "
                                "aday etkinleştirilmedi.")
                        else:
                            st.info(
                                "Döngü tamamlandı ancak aday sabit testlerde "
                                "iyileşme eşiğini geçmedi; aktif hafıza değişmedi.")
                    else:
                        saved, record = _persist_mutation(lambda: AgentReviewLoop(colony).execute(
                            selected, reviewer, review_goal,
                            client=AnswerAdapter(answer), model="configured-provider"))
                        if not saved:
                            return
                        st.session_state["colony_last_review"] = record
                        st.success("Üç model çağrısı tamamlandı; inceleme kaydı oluşturuldu.")
                except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
                    st.error("İnceleme döngüsü tamamlanamadı; aktif dersler değişmedi.")
            cycle = st.session_state.get("cano_improvement_cycle")
            if cycle and cycle["status"] == "blocked":
                st.caption(
                    "İnceleme kaydı korundu. Model sağlayıcısı veya test işlemi "
                    "tamamlanamadı; aktif hafızaya hiçbir ders eklenmedi.")
            elif cycle:
                st.caption(
                    f"Test sonucu: aday {cycle['benchmark']['candidate_passed']}/"
                    f"{cycle['benchmark']['total_cases']}, mevcut bellek "
                    f"{cycle['benchmark']['baseline_passed']}/"
                    f"{cycle['benchmark']['total_cases']}; fark "
                    f"{cycle['benchmark']['delta']:+.0%}. "
                    f"Tekrar tutarlılığı: {cycle['benchmark']['reproducible']}; "
                    f"gerileme: {len(cycle['benchmark']['regressed_case_ids'])}.")
                if cycle["status"] == "review_pending":
                    st.text_area(
                        "İnceleme bekleyen ders adayı", value=cycle["lesson"],
                        disabled=True, key="cano_pending_improvement_lesson")
                    if st.button("Bu dersi sonraki görevlerde kullanmayı onayla",
                                 key="cano_approve_improvement_lesson"):
                        try:
                            saved, approved = _persist_mutation(lambda:
                                colony.approve_feedback(
                                    cycle["feedback_id"], approved=True))
                            if saved:
                                st.success(
                                    "Ders kabul edildi; bu uzmanın sonraki görevlerinde "
                                    "hafıza bağlamına eklenecek. Model ağırlıkları değişmedi.")
                                st.session_state.pop("cano_improvement_cycle", None)
                                st.rerun()
                        except (KeyError, ValueError, PermissionError, sqlite3.Error):
                            st.error("Ders onaylanamadı; etkin hafıza değişmedi.")
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
                    mission_manager = CollaborativeMission(colony)
                    mission = mission_manager.execute(
                        mission_goal, client=AnswerAdapter(answer),
                        model="configured-provider",
                        source_lookup=scientific_sources if crossref_opt_in else None,
                        on_checkpoint=_stage_checkpoint_callback())
                    # The fourth stage's completion status must also be durable.
                    _checkpoint(archive_prior=False)
                    st.session_state["colony_last_mission"] = mission
                    st.success("Dört aşamalı ekip görevi tamamlandı; bağımsız doğrulama bekliyor.")
                except (ValueError, RuntimeError, OSError, sqlite3.Error) as exc:
                    st.error(mission_failure_message(
                        exc, getattr(mission_manager, "last_failure", None)))
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
                        saved, _ = _persist_mutation(
                            lambda: manager.inspect_source_documents(mission["id"]))
                        if not saved:
                            return
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
                                    OSError, sqlite3.Error) as exc:
                                st.error(mission_failure_message(
                                    exc, getattr(mission_manager, "last_failure", None)))
                if any(item["status"] == "running" for item in interrupted):
                    if st.button("1 saatten eski yarım görevleri kurtarmaya aç",
                                 key="recover_stale_colony_missions"):
                        try:
                            saved, recovered = _persist_mutation(
                                lambda: mission_manager.recover_stale(older_than_seconds=3600))
                            if not saved:
                                return
                            st.info(f"{len(recovered)} eski görev yeniden denemeye açıldı.")
                            st.rerun()
                        except (ValueError, RuntimeError, OSError, sqlite3.Error):
                            st.error("Yarım görev kurtarma tamamlanamadı; yerel kayıtlar korundu.")
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
                                 "eski kayıtların üzerine yazılmadı. Komuta Merkezi'ndeki "
                                 "şifreli dış yedeği alın.")
            if st.button("Kalıcı yedeği kontrol et", key="colony_postgres_check"):
                try:
                    saved = ColonySnapshotStore(database_url).load(owner_key)
                    if snapshots_match(saved, data):
                        st.success("Yedek mevcut ve bu oturumun bütün kayıtlarıyla eşleşiyor.")
                    elif saved is None:
                        st.warning("Bu kullanıcı için kalıcı yedek bulunamadı.")
                    else:
                        st.warning("Yedek mevcut ama bu oturumun kayıtlarından farklı; güncel olduğu doğrulanmadı.")
                except Exception:
                    st.error("Kalıcı yedek okunamadı.")
        if not (owner_key and database_url):
            st.download_button("Ajanları ve dersleri yedekle (şifrelenmemiş JSON)",
                               data=json.dumps(data, ensure_ascii=False, indent=2),
                               file_name="ajan-kolonisi-yedek.json",
                               mime="application/json", key="colony_backup")
