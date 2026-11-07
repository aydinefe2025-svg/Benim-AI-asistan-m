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
from core.claim_evidence import (
    audit_claim_quotes, has_readable_source_excerpt, record_source_claim_review,
    retry_unavailable_skeptical_pass,
)
from core.claim_review_benchmark import run_claim_review_benchmark
from core.evidence_appraisal import record_claim_evidence_appraisal
from core.groq_team import TeamRateLimitError
from core.groq_claim_json import (
    generate_claim_quote_json, generate_claim_verification_json,
)
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
    candidates = db.execute(
        "SELECT id,task,stages FROM colony_missions WHERE status=? "
        "ORDER BY created_at DESC LIMIT 12",
        ("review_pending",)).fetchall()
missions = [mission for mission in candidates
            if has_readable_source_excerpt(mission["stages"])]
restore_notice = st.session_state.pop("_cano_evidence_restore_notice", None)
if restore_notice:
    st.warning(restore_notice)
if not missions:
    # Each new Streamlit session gets an isolated SQLite database. Restore only
    # the signed-in owner's backup, and only into an empty local colony.
    with colony._db() as db:
        local_agent_count = db.execute("SELECT COUNT(*) FROM colony_agents").fetchone()[0]
    restore_attempt_key = "_cano_evidence_restore_attempted_owner"
    restore_attempted = st.session_state.get(restore_attempt_key) == owner
    if owner and not local_agent_count and not restore_attempted:
        st.session_state[restore_attempt_key] = owner
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
            st.warning("Eski CANO yedeğinde gerekli alanlar eksik; mevcut kayıtlar ve kalıcı yedek korundu.")
        except KeyError:
            st.warning("Yedek kaydının beklenen alanı eksik; mevcut kayıtlar ve kalıcı yedek korundu.")
        except LookupError:
            st.info("Bu hesap için eşleşen CANO yedeği bulunamadı. Yeni görevler ana CANO ekranından oluşturulabilir.")
        except PermissionError:
            st.warning("Kalıcı yedek erişim izni doğrulanamadı; hiçbir kayıt değiştirilmedi.")
        except RuntimeError:
            st.warning("Geri yükleme güvenli biçimde durdu; mevcut kayıtlar ve kalıcı yedek korundu.")
        except OSError:
            st.warning("Yerel oturum depolaması kullanılamadı; kalıcı yedek değiştirilmedi.")
        except Exception:
            st.error("Kalıcı yedek servisi kullanılamıyor; hiçbir kayıt değiştirilmedi.")
        else:
            st.success(f"{restored} CANO rol kaydı güvenli biçimde geri yüklendi.")
            if skipped:
                st.session_state["_cano_evidence_restore_notice"] = (
                    f"{skipped} eksik eski görev kaydı mevcut görev tablosuna alınamadı. "
                    "Özgün yedek, sürüm geçmişine arşivlendi ve korundu.")
            st.rerun()
    elif owner and not local_agent_count and restore_attempted:
        st.info("Bu oturumda kaynak denetimi görevi yok. Hesabın yedeği otomatik kontrol edildi.")
        if st.button("Hesabıma ait CANO yedeğini yeniden dene", key="cano_evidence_restore_retry"):
            st.session_state.pop(restore_attempt_key, None)
            st.rerun()
    else:
        st.info("Bu oturumda okunabilir kaynak metni olan inceleme bekleyen görev yok. Önce ana CANO ekranında kaynaklı araştırma görevini ve kaynak okuma işlemini tamamlayın. Mevcut kayıtların üzerine yedek yüklenmez.")
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
if documents and st.button("Görevdeki DOI kaynaklarını yeniden oku"):
    try:
        if owner:
            store = ColonySnapshotStore(cano_database_url(os.environ))
            store.verify_schema()
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony))
        manager.inspect_source_documents(mid, refresh_missing=True)
        if owner:
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony),
                                  archive_prior=False)
        st.rerun()
    except (ValueError, PermissionError, RuntimeError, OSError, sqlite3.Error):
        st.warning("Kaynaklar yenilenemedi; önceki okunabilir alıntılar korundu.")
key = os.environ.get("GROQ_API_KEY")
if not key:
    try:
        key = st.secrets.get("GROQ_API_KEY")
    except Exception:
        key = None

class Client:
    def chat(self, model, system, prompt):
        return generate_claim_quote_json(system, prompt, api_key=key)

    def verify(self, model, system, prompt):
        return generate_claim_verification_json(system, prompt, api_key=key)

if documents and key and st.button("İddiaları çıkar ve ayrı kuşkucu AI geçişi çalıştır (en fazla 2 çağrı)"):
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

st.divider()
st.subheader("Bağımsız CANO testi ve kör insan karşılaştırması")
from core.claim_review_benchmark import (
    CASES as FIXED_BENCHMARK_CASES,
    HUMAN_COMPARISON_CASES, SUPPLEMENTAL_COMPARISON_CASES,
    load_expected_labels, score_labels,
)
st.markdown("### 12 vakalık canlı model testi")
st.caption(
    "Bu sabit sentetik test, Groq JSON yanıtını tek çağrıda doğrular ve bu küçük "
    "kümedeki sonucu gösterir. İnsan etiketi istemez, CANO görev kayıtlarını "
    "değiştirmez ve kör insan karşılaştırmasının yerine geçmez."
)
runtime_benchmark_key = "cano_claim_review_runtime_smoke_v1"
if key and st.button("CANO modelini 12 sabit vakada test et (1 çağrı)"):
    try:
        runtime_result = run_claim_review_benchmark(
            Client(), cases=FIXED_BENCHMARK_CASES)
    except TeamRateLimitError:
        st.warning("Canlı model testi kotaya takıldı; CANO görev kayıtları değiştirilmedi.")
    except (ValueError, RuntimeError) as err:
        st.warning(
            f"Canlı model testi tamamlanamadı ({type(err).__name__}: {err}); "
            "CANO görev kayıtları değiştirilmedi."
        )
    else:
        st.session_state[runtime_benchmark_key] = runtime_result
runtime_result = st.session_state.get(runtime_benchmark_key)
if isinstance(runtime_result, dict):
    st.metric(
        "12 vaka · sabit sentetik kümede doğru karar",
        f"{runtime_result['correct']} / {runtime_result['total']}",
        f"%{runtime_result['accuracy'] * 100:.0f}",
    )
    st.metric("Yanıt kapsamı", f"%{runtime_result['coverage'] * 100:.0f}")
    st.caption(runtime_result["scope"])
    st.json(runtime_result["confusion_matrix"])
    if runtime_result["unscored"]:
        st.warning(f"{runtime_result['unscored']} vaka yanıtlanmadı; hata olarak sayıldı.")

st.caption(
    "8 yayımlanmış makaleden kaynak bağlantılı 24 vaka; 8 destek, 8 çelişki ve 8 yetersiz kanıt. Bunlar 24 ayrı makale değildir. "
    "Önce iddia ve pasajları, beklenen/model kararları gösterilmeden inceleyin. "
    "Tüm insan etiketleri gönderilmeden model testi çalışmaz. Sonuç yalnızca bu "
    "küçük kaynak-temelli kümeye ve tek insan değerlendiriciye aittir; gerçek dünya "
    "genel bilimsel doğruluğu veya insan üstünlüğünü kanıtlamaz."
)
label_key = "cano_claim_review_human_labels_v3"
model_key = "cano_claim_review_human_benchmark_v3"
with st.form("cano_blind_human_labels_v3"):
    human_labels = {}
    for idx, case in enumerate(HUMAN_COMPARISON_CASES):
        st.markdown(f"**Vaka {idx + 1}.** {case['claim']}")
        st.caption(case["excerpt"])
        st.markdown(f"[Kaynağı aç: {case['source_title']}]({case['source_url']})")
        choice = st.selectbox(
            "Pasajın iddiaya göre durumu",
            ["— Seçin —", "Destekliyor", "Çelişiyor", "Kanıt yetersiz"],
            key=f"cano_human_v3_{case['case_id']}",
        )
        human_labels[case["case_id"]] = {
            "Destekliyor": "supported",
            "Çelişiyor": "contradicted",
            "Kanıt yetersiz": "insufficient",
        }.get(choice, "")
    labels_submitted = st.form_submit_button("24 insan değerlendirmesini kaydet")
if labels_submitted:
    if any(not value for value in human_labels.values()):
        st.warning("Karşılaştırma için 24 vakanın tamamını etiketleyin.")
    else:
        st.session_state[label_key] = human_labels
        st.session_state.pop(model_key, None)
        st.success("Etiketler bu tarayıcı oturumunda saklandı; beklenen cevaplar etiketleme sırasında gösterilmedi.")
saved_human_labels = st.session_state.get(label_key)
try:
    human_answer_key = load_expected_labels(
        os.environ.get("CANO_HUMAN_BENCHMARK_ANSWER_KEY"))
except (ValueError, RuntimeError):
    human_answer_key = None
if isinstance(saved_human_labels, dict) and set(saved_human_labels) == {
        case["case_id"] for case in HUMAN_COMPARISON_CASES}:
    if human_answer_key is None:
        st.warning("Kör karşılaştırmanın sunucu cevap anahtarı ayarlı değil; etiketler bu oturumda korunuyor, skor ve model testi kapalı.")
    else:
        human_score = score_labels(
            HUMAN_COMPARISON_CASES, saved_human_labels, human_answer_key)
        st.metric("İnsan değerlendirici · altın etikete uyum",
                  f"{human_score['correct']} / {human_score['total']}",
                  f"%{human_score['accuracy'] * 100:.0f}")
        st.caption("Tek insan değerlendirici; vaka başına bağımsız ikinci insan puanlaması yok.")
        st.caption("İnsan etiketlerinin sınıf bazlı sonuçları")
        st.json(human_score["confusion_matrix"])
        if key and st.button("Etiketlerden sonra CANO modelini çalıştır (24 vaka, 1 çağrı)"):
            try:
                result = run_claim_review_benchmark(
                    Client(), cases=HUMAN_COMPARISON_CASES,
                    expected_labels=human_answer_key)
            except TeamRateLimitError:
                st.warning("Model kotası nedeniyle test tamamlanamadı; insan etiketleri bu oturumda korundu.")
            except (ValueError, RuntimeError) as err:
                st.warning(f"Model testi tamamlanamadı ({type(err).__name__}: {err}); insan etiketleri korundu.")
            else:
                st.session_state[model_key] = result
        model_result = st.session_state.get(model_key)
        if isinstance(model_result, dict):
            human_by_id = saved_human_labels
            model_by_id = {case["case_id"]: case["predicted"] for case in model_result["cases"]}
            agreement = sum(human_by_id[c["case_id"]] == model_by_id[c["case_id"]]
                            for c in HUMAN_COMPARISON_CASES)
            st.metric("CANO modeli · aynı 24 vakanın altın etiketine uyum",
                      f"{model_result['correct']} / {model_result['total']}",
                      f"%{model_result['accuracy'] * 100:.0f}")
            st.metric("İnsan–CANO karar uyumu", f"{agreement} / {len(HUMAN_COMPARISON_CASES)}")
            st.caption("Öneri ve denetim aynı Groq model sağlayıcısını kullanıyor; ikinci geçiş bağımsız model kanıtı değildir.")
            st.caption(model_result["scope"])
            st.json(model_result["confusion_matrix"])
            if model_result["unscored"]:
                st.warning(f"{model_result['unscored']} cevaplanmayan vaka hata sayıldı.")
elif isinstance(st.session_state.get("cano_claim_review_benchmark_result"), dict):
    st.info("Önceki 12 vakalık sonuç yalnızca aynı küçük sabit kümenin testidir; bağımsız 24 vaka ve insan karşılaştırması yerine geçmez.")

st.markdown("### Ek kör kohort · 24 vaka, 8 yeni yayın")
st.caption(
    "Önceki 24 vakadan farklı sekiz yayın. Her yayından bir destek, bir çelişki "
    "ve bir yetersiz kanıt vakası var. İnsan yanıtları ve altın etiketler bu "
    "ek kohort için ayrı tutulur. Bu küçük küme genel bilimsel doğruluğu veya "
    "insan üstünlüğünü kanıtlamaz."
)
v4_label_key = "cano_claim_review_human_labels_v4"
v4_model_key = "cano_claim_review_human_benchmark_v4"
with st.form("cano_blind_human_labels_v4"):
    v4_human_labels = {}
    for idx, case in enumerate(SUPPLEMENTAL_COMPARISON_CASES):
        st.markdown(f"**Ek vaka {idx + 1}.** {case['claim']}")
        st.caption(case["excerpt"])
        st.markdown(f"[Kaynağı aç: {case['source_title']}]({case['source_url']})")
        choice = st.selectbox(
            "Pasajın iddiaya göre durumu",
            ["— Seçin —", "Destekliyor", "Çelişiyor", "Kanıt yetersiz"],
            key=f"cano_human_v4_{case['case_id']}",
        )
        v4_human_labels[case["case_id"]] = {
            "Destekliyor": "supported",
            "Çelişiyor": "contradicted",
            "Kanıt yetersiz": "insufficient",
        }.get(choice, "")
    v4_labels_submitted = st.form_submit_button("Ek 24 insan değerlendirmesini kaydet")
if v4_labels_submitted:
    if any(not value for value in v4_human_labels.values()):
        st.warning("Ek kohort için 24 vakanın tamamını etiketleyin.")
    else:
        st.session_state[v4_label_key] = v4_human_labels
        st.session_state.pop(v4_model_key, None)
        st.success("Ek kohort etiketleri bu tarayıcı oturumunda saklandı; cevap anahtarı gösterilmedi.")
v4_saved_labels = st.session_state.get(v4_label_key)
try:
    v4_answer_key = load_expected_labels(
        os.environ.get("CANO_HUMAN_BENCHMARK_ANSWER_KEY_V4"),
        SUPPLEMENTAL_COMPARISON_CASES,
    )
except (ValueError, RuntimeError):
    v4_answer_key = None
if isinstance(v4_saved_labels, dict) and set(v4_saved_labels) == {
        case["case_id"] for case in SUPPLEMENTAL_COMPARISON_CASES}:
    if v4_answer_key is None:
        st.warning(
            "Ek kohortun özel cevap anahtarı ayarlı değil; etiketler korunuyor, "
            "skor ve model testi kapalı."
        )
    else:
        v4_human_score = score_labels(
            SUPPLEMENTAL_COMPARISON_CASES, v4_saved_labels, v4_answer_key)
        st.metric(
            "Ek kohort · insan değerlendiricinin altın etikete uyumu",
            f"{v4_human_score['correct']} / {v4_human_score['total']}",
            f"%{v4_human_score['accuracy'] * 100:.0f}",
        )
        st.caption("Tek değerlendirici; vaka başına ikinci bağımsız insan puanlaması yok.")
        st.json(v4_human_score["confusion_matrix"])
        if key and st.button("Ek kohortta CANO modelini çalıştır (24 vaka, 1 çağrı)"):
            try:
                v4_result = run_claim_review_benchmark(
                    Client(), cases=SUPPLEMENTAL_COMPARISON_CASES,
                    expected_labels=v4_answer_key,
                )
            except TeamRateLimitError:
                st.warning("Model kotası nedeniyle ek test tamamlanamadı; insan etiketleri korundu.")
            except (ValueError, RuntimeError) as err:
                st.warning(
                    f"Ek model testi tamamlanamadı ({type(err).__name__}: {err}); "
                    "insan etiketleri korundu."
                )
            else:
                st.session_state[v4_model_key] = v4_result
        v4_model_result = st.session_state.get(v4_model_key)
        if isinstance(v4_model_result, dict):
            v4_model_by_id = {
                case["case_id"]: case["predicted"]
                for case in v4_model_result["cases"]
            }
            v4_agreement = sum(
                v4_saved_labels[case["case_id"]] == v4_model_by_id[case["case_id"]]
                for case in SUPPLEMENTAL_COMPARISON_CASES
            )
            st.metric(
                "Ek kohort · CANO'nun altın etikete uyumu",
                f"{v4_model_result['correct']} / {v4_model_result['total']}",
                f"%{v4_model_result['accuracy'] * 100:.0f}",
            )
            st.metric("Ek kohort · insan–CANO karar uyumu", f"{v4_agreement} / 24")
            st.caption(
                "İddia denetimi ve benchmark aynı Groq sağlayıcısını kullanır; "
                "bu sonuç bağımsız model doğrulaması değildir."
            )
            st.caption(v4_model_result["scope"])
            st.json(v4_model_result["confusion_matrix"])
            if v4_model_result["unscored"]:
                st.warning(
                    f"{v4_model_result['unscored']} yanıtsız model kararı hata sayıldı."
                )

if not key:
    st.warning("Model bağlantısı yok; yeni iddia denetimi çalıştırılmadı.")
reviewed_mission = manager.get(mid)
unavailable_passes = [
    index for index, item in enumerate(reviewed_mission["stages"][0].get("source_claim_audit", []))
    if item.get("status") == "quote_found_unverified"
    and isinstance(item.get("machine_assessment"), dict)
    and item["machine_assessment"].get("available") is False
]
if unavailable_passes and key and st.button("Kuşkucu geçişi yeniden dene (1 çağrı)", key="cano_retry_skeptical_pass"):
    try:
        if owner:
            store = ColonySnapshotStore(cano_database_url(os.environ))
            store.verify_schema()
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony))
        retry_unavailable_skeptical_pass(
            manager, mid, client=Client(), model="configured-provider")
        if owner:
            save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony),
                                  archive_prior=False)
        st.rerun()
    except (ValueError, RuntimeError, TeamRateLimitError) as err:
        st.warning("Kuşkucu geçiş tamamlanamadı; önceki alıntı ve inceleme kaydı korundu.")
        st.caption(f"Güvenli hata ayrıntısı: {type(err).__name__}: {err}")
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
        assessment = item.get("machine_assessment")
        if isinstance(assessment, dict):
            if assessment.get("available") is False:
                st.warning("Kuşkucu AI geçişi alınamadı; alıntı eşleşmesi korundu ve iddia doğrulanmış sayılmıyor.")
            else:
                verdict_labels = {
                    "supported": "Kuşkucu AI geçişi: pasaj iddiayı doğrudan destekliyor",
                    "contradicted": "Kuşkucu AI geçişi: pasaj iddiayla çelişiyor",
                    "insufficient": "Kuşkucu AI geçişi: pasaj yetersiz veya belirsiz",
                }
                st.info(verdict_labels.get(assessment.get("verdict"),
                                           "İkinci model incelemesi: karar yok"))
            st.caption(str(assessment.get("reason", ""))
                       + " Bu model değerlendirmesi otomatik doğrulama değildir.")
        st.link_button("Kaynağı aç", item["citation_url"])
        if item.get("comparison_status") == "model_suggested":
            labels = {
                "supports": "Pasaj iddiayı destekliyor olabilir",
                "contradicts": "Pasaj iddiayla çelişiyor olabilir",
                "correction_or_context": "Pasaj düzeltme veya önemli bağlam sunuyor",
                "insufficient": "Pasaj iddiayı değerlendirmek için yetersiz",
            }
            label = labels.get(item.get("comparison"), labels["insufficient"])
            st.info("CANO'nun geçici metin yorumu: " + label)
            if item.get("comparison_rationale"):
                st.caption(item["comparison_rationale"])
            st.caption(
                "Bu, model önerisidir; bağımsız bilimsel doğrulama veya insan kararı değildir.")
        else:
            st.info("İddia ile pasaj arasındaki ilişki değerlendirilmedi; yalnızca alıntı bulundu.")
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
    if (owner and item.get("status") == "quote_found_unverified"
            and isinstance(source, dict) and source.get("status") == "full_text_excerpt"):
        with st.expander("Bilimsel kanıt profilini kaydet (insan değerlendirmesi)", expanded=False):
            st.caption("Bu kayıt çalışma özelliklerini ve belirsizlikleri görünür kılar; evrensel kalite puanı üretmez ve iddiayı otomatik doğrulamaz.")
            design_labels = {
                "Randomize kontrollü çalışma": "randomized_trial",
                "Gözlemsel çalışma": "observational",
                "Sistematik derleme / meta-analiz": "systematic_review",
                "Nitel araştırma": "qualitative",
                "Olgu sunumu": "case_report",
                "Hesaplamalı / simülasyon": "computational",
                "Ön baskı": "preprint",
                "Diğer": "other",
                "Belirsiz": "unclear",
            }
            with st.form(f"evidence_appraisal_{mid}_{claim_index}"):
                design_label = st.selectbox("Çalışma tasarımı", list(design_labels))
                population = st.text_input("Popülasyon / incelenen sistem (bilinmiyorsa 'belirsiz')", max_chars=1000)
                sample_size = st.text_input("Örneklem ve analiz birimi", max_chars=1000)
                comparator = st.text_input("Karşılaştırıcı / kontrol", max_chars=1000)
                outcome = st.text_input("Tam olarak ölçülen sonuç", max_chars=1000)
                effect_estimate = st.text_input("Etki tahmini ve birim", max_chars=1000)
                uncertainty = st.text_input("Belirsizlik (CI, aralık, hata ölçüsü veya 'raporlanmamış')", max_chars=1000)
                preregistration_label = st.selectbox("Ön kayıt / protokol", ["Evet", "Hayır", "Belirsiz", "Uygulanamaz"])
                replication_label = st.selectbox("Bağımsız tekrar", ["Var", "Yok", "Belirsiz", "Uygulanamaz"])
                conflicts_label = st.selectbox("Çelişen bulgular", ["Var", "Yok", "Belirsiz", "Uygulanamaz"])
                limitations = st.text_area("Başlıca sınırlılıklar ve olası yanlılıklar", max_chars=1000)
                rob = None
                if design_labels[design_label] == "randomized_trial":
                    st.caption("RoB 2 yalnızca randomize çalışmanın belirli bir sonucu için; her alanı metindeki gerekçeyle doldurun.")
                    rob = {}
                    rob_domains = {
                        "randomization": "Randomizasyon süreci",
                        "deviations_from_interventions": "Müdahaleden sapmalar",
                        "missing_outcome_data": "Eksik sonuç verisi",
                        "outcome_measurement": "Sonuç ölçümü",
                        "selective_reporting": "Seçici sonuç raporlama",
                    }
                    for domain, label in rob_domains.items():
                        judgement = st.selectbox(
                            label + " — endişe düzeyi",
                            ["Düşük", "Bazı endişeler", "Yüksek", "Belirsiz"],
                            key=f"rob_judgement_{mid}_{claim_index}_{domain}")
                        reason = st.text_input(
                            label + " — metinsel gerekçe",
                            max_chars=500,
                            key=f"rob_reason_{mid}_{claim_index}_{domain}")
                        rob[domain] = {
                            "judgement": {
                                "Düşük": "low", "Bazı endişeler": "some_concerns",
                                "Yüksek": "high", "Belirsiz": "unclear",
                            }[judgement],
                            "rationale": reason,
                        }
                submitted_appraisal = st.form_submit_button("Kanıt profilini kaydet")
            if submitted_appraisal:
                tri = {"Evet": "yes", "Hayır": "no", "Belirsiz": "unclear", "Uygulanamaz": "not_applicable"}
                profile = {
                    "study_design": design_labels[design_label],
                    "population": population, "sample_size": sample_size,
                    "comparator": comparator, "outcome": outcome,
                    "effect_estimate": effect_estimate, "uncertainty": uncertainty,
                    "limitations": limitations,
                    "preregistration": tri[preregistration_label],
                    "independent_replication": tri[replication_label],
                    "conflicting_evidence": tri[conflicts_label],
                }
                if rob is not None:
                    profile["risk_of_bias"] = rob
                try:
                    store = ColonySnapshotStore(cano_database_url(os.environ))
                    store.verify_schema()
                    save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony))
                    record_claim_evidence_appraisal(
                        manager, mid, claim_index, reviewer_id=owner, profile=profile)
                    save_owner_checkpoint(store, owner, st.session_state, _snapshot(colony),
                                          archive_prior=False)
                except (ValueError, PermissionError, RuntimeError, OSError, sqlite3.Error):
                    st.warning("Kanıt profili kaydedilemedi; önceki kayıtlar korundu.")
                else:
                    st.success("Kanıt profili insan değerlendirmesi olarak kaydedildi; iddia durumu otomatik değiştirilmedi.")
                    st.rerun()
        appraisal = item.get("evidence_appraisal")
        if isinstance(appraisal, dict):
            profile = appraisal.get("profile", {})
            st.info("Kayıtlı kanıt profili · " + str(profile.get("study_design", "belirsiz"))
                    + " · tekrar: " + str(profile.get("independent_replication", "belirsiz"))
                    + " · çelişen bulgular: " + str(profile.get("conflicting_evidence", "belirsiz")))
            st.caption("Ölçülen sonuç: " + str(profile.get("outcome", ""))
                       + " · Etki: " + str(profile.get("effect_estimate", ""))
                       + " · Belirsizlik: " + str(profile.get("uncertainty", "")))

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

