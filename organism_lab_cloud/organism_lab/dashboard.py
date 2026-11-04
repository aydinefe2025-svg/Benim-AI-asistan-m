"""Streamlit dashboard for the digital organism lab (local or hosted demo)."""
from pathlib import Path
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from uuid import uuid4

# Streamlit launches this file directly; ensure repository imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from organism_lab.shared_world import run_shared_world
from organism_lab.reproduction_study import run_study, save_study
from organism_lab.adaptation_study import run_adaptation_study, save_adaptation_study
from organism_lab.literature_search import list_records, save_records, search_openalex
from organism_lab.persistent_memory import (augment_with_memory, list_memories,
                                            retrieve_memories, save_memory)
from organism_lab.providers import (GROQ_MODEL_OPTIONS, ProviderError, diagnose_groq_access,
                                    generate, groq_active_key, groq_test_key, trained_local_ready)
from organism_lab.agent_roles import AGENT_PROFILES, profile_prompt
from organism_lab.cloud_runtime import default_provider, session_output_dir

CLOUD_MODE = os.environ.get("ORGANISM_LAB_CLOUD_MODE", "").strip() == "1"
st.set_page_config(page_title="Organizma Laboratuvarı", layout="wide")
_archive = None
_archive_baseline = None
_owner_key = None
if CLOUD_MODE:
    from organism_lab.persistent_store import (
        PostgresArchive, PersistenceConflict, authenticated_owner_key,
        pack_directory, unpack_directory,
    )
    if os.environ.get("ORGANISM_LAB_OIDC_CONFIGURED") != "1":
        st.title("Organizma Laboratuvarı")
        st.error("Kalıcı bulut laboratuvarı güvenli giriş ayarları tamamlanana kadar kapalı.")
        st.stop()
    required = ("DATABASE_URL", "ORGANISM_LAB_OWNER_EMAIL", "ORGANISM_LAB_OWNER_KEY_SECRET")
    if any(not os.environ.get(name, "").strip() for name in required):
        st.title("Organizma Laboratuvarı")
        st.error("Kalıcı veritabanı ve hesap sahipliği yapılandırması tamamlanana kadar bulut kullanımı kapalı.")
        st.stop()
    if not st.user.is_logged_in:
        st.title("Organizma Laboratuvarı")
        st.button("Google ile güvenli giriş", on_click=st.login)
        st.stop()
    try:
        _owner_key = authenticated_owner_key(
            st.user,
            allowed_email=os.environ["ORGANISM_LAB_OWNER_EMAIL"],
            secret=os.environ["ORGANISM_LAB_OWNER_KEY_SECRET"],
        )
        _archive = PostgresArchive(_owner_key)
        _archive.check()
    except Exception:
        st.error("Hesap doğrulanamadı veya kalıcı arşive erişilemiyor. Veriler korunuyor.")
        if st.button("Oturumu kapat"):
            st.logout()
        st.stop()
    OUTPUT_DIR = session_output_dir(
        os.environ.get("ORGANISM_LAB_OUTPUT_DIR", "/tmp/organism-lab-sessions"),
        st.session_state,
    )
    try:
        if not st.session_state.get("organism_lab_archive_conflict"):
            _snapshot, _archive_baseline = _archive.load()
            if _snapshot is not None:
                unpack_directory(_snapshot, OUTPUT_DIR)
            st.session_state["organism_lab_archive_baseline"] = _archive_baseline
    except Exception:
        st.error("Kalıcı arşiv okunamadı veya bütünlük kontrolü başarısız. Oturum durduruldu.")
        st.stop()
else:
    OUTPUT_DIR = Path(os.environ.get(
        "ORGANISM_LAB_OUTPUT_DIR",
        Path(__file__).resolve().parents[3] / "organism_lab_output",
    )).resolve()
st.title("Organizma Laboratuvarı")
st.caption("Yalnızca dijital simülasyon. Fiziksel robot veya biyolojik organizma kontrolü içermez.")
if CLOUD_MODE:
    st.caption(
        "Hesap başına kalıcı laboratuvar arşivi etkin. Her kayıt Neon PostgreSQL'de "
        "kullanıcıya özel anahtarla saklanır; yedekleri düzenli olarak indirin. "
        "Yerel Ollama/LoRA modeli bulut sunucusunda çalışmaz."
    )
    if st.button("Oturumu kapat", key="organism_lab_logout"):
        st.logout()

st.header("Araştırma asistanı ve kalıcı arşiv" if CLOUD_MODE else "Yerel asistan ve kalıcı hafıza")
st.caption(
    "Açıkça kaydedilen notlar kalıcı ve hesaba özel arşivde tutulur. "
    "Sohbetler model ağırlıklarını eğitmez; notlar bağımsız doğrulanmış değildir."
    if CLOUD_MODE else
    "Ham sohbetler kendiliğinden eğitime katılmaz. Burada açıkça kaydettiğin notlar bu bilgisayardaki SQLite belleğinde tutulur. Kalıcı bellek ile ağırlık eğitimi ayrı şeylerdir; notlar bağımsız doğrulanmış değildir."
)
adapter_ready = not CLOUD_MODE and trained_local_ready()
if adapter_ready:
    st.warning("LoRA adaptörü hazır, ancak yalnızca 8 örnekle eğitildi ve yanıt kalitesi henüz doğrulanmadı. Varsayılan olarak Ollama Qwen3:8B kullanılır; adaptörü aşağıdan deneyebilirsin.")
    model_choices = {
        "ollama": "Ollama Qwen3:8B (önerilen)",
        "trained_local": "Deneysel LoRA Qwen3-0.6B",
    }
    selected_provider = st.selectbox(
        "Sohbet modeli", options=list(model_choices),
        format_func=lambda value: model_choices[value], key="assistant_model_choice",
    )
    selected_model = None
elif CLOUD_MODE:
    groq_configured = bool(groq_active_key())
    test_key = groq_test_key()
    test_key_active = os.environ.get("GROQ_API_KEY_TEST_ACTIVE", "").strip() == "1"
    if groq_configured:
        active_label = "ayrı test anahtarı" if test_key_active else "mevcut Groq anahtarı"
        st.info(f"Bulut sohbeti Groq üzerinden çalışır ({active_label}); gönderdiğin soru ve kullanılan açıkça kaydedilmiş notlar sağlayıcıya iletilir.")
    else:
        st.info("Model seçeneklerini inceleyebilirsin. Sohbet, sunucuya güvenli Groq anahtarı eklenene kadar kapalıdır; API çağrısı yapılmaz.")
    selected_provider = "groq"
    selected_model = st.selectbox(
        "Groq modeli", options=GROQ_MODEL_OPTIONS, index=0, key="assistant_groq_model",
        help="Büyük modeller daha fazla kota/tüketim kullanabilir. Model çağrısı yalnızca sen Yanıt üret'e bastığında yapılır.",
    )
    st.caption("Model erişimi ve ücret/kota koşulları Groq hesabına bağlıdır. Kullanılmayan modeller için otomatik çağrı yapılmaz.")
    diagnostic_key = test_key or os.environ.get("GROQ_API_KEY", "")
    diagnostic_label = "ayrı test anahtarı" if test_key else "mevcut Groq anahtarı"
    if diagnostic_key.strip() and st.button("Groq proje erişimini tanıla", key="diagnose_groq_project"):
        diagnosis = diagnose_groq_access(
            diagnostic_key, selected_model,
        )
        if diagnosis["reachable"] and diagnosis["model_available"]:
            st.success(f"Render'daki {diagnostic_label} Groq'a erişiyor ve seçili model listeleniyor. Sohbet anahtarını değiştirmek için GROQ_API_KEY_TEST_ACTIVE değerini 1 yapıp yeniden dağıtabilirsin.")
        elif diagnosis["reachable"]:
            st.error(f"Render'daki {diagnostic_label} erişiyor, ancak seçili model bu anahtarın projesinde listelenmiyor.")
        else:
            status = diagnosis["http_status"]
            code = diagnosis["error_code"]
            safe_status = f"HTTP {status}" if isinstance(status, int) else "ağ yanıtı yok"
            safe_code = f" · Groq kodu: {code}" if code else ""
            st.error(f"Render'daki {diagnostic_label} ile Groq model listesi isteği başarısız ({safe_status}{safe_code}). Anahtar değeri gösterilmedi.")
else:
    st.info("Şu an Ollama temel modeli kullanılıyor; bu bilgisayarda eğitilmiş bir adaptör etkin değil. Kaydedilen notlar yanıta bağlam olarak eklenir, model ağırlıklarını değiştirmez.")
    selected_provider = "ollama"
    selected_model = None
try:
    research_status = json.loads((OUTPUT_DIR / "continuous_research_status.json").read_text(encoding="utf-8"))
    completed_cycles = research_status.get("last_completed_cycle", 0)
    if isinstance(completed_cycles, int) and not isinstance(completed_cycles, bool):
        cycle_state = "çalışıyor" if research_status.get("status") == "running" else str(research_status.get("status", "durum bilinmiyor"))
        st.caption(f"Arka plan araştırması: {cycle_state} · {completed_cycles} çevrim tamamlandı. Bu, sanal deney döngüsüdür; sohbet modelinin ağırlıklarını eğitmez.")
except (OSError, ValueError, TypeError):
    st.caption("Arka plan araştırma durumu henüz kaydedilmedi.")
memory_topic = st.text_input("Not başlığı", max_chars=100, key="memory_topic")
memory_content = st.text_area("Asistanın sonraki oturumlarda hatırlamasını istediğin bilgi", max_chars=4000,
                              key="memory_content")
save_memory_clicked = st.button("Notu kalıcı hafızaya kaydet", key="save_assistant_memory")
if save_memory_clicked:
    try:
        note = save_memory(OUTPUT_DIR, memory_topic, memory_content)
        location = "hesaba ait kalıcı arşivde" if CLOUD_MODE else "yalnızca yerel bilgisayarda"
        st.success(f"Not kaydedildi · #{note['id']} · {location}")
    except (OSError, ValueError) as exc:
        st.error(f"Not kaydedilemedi ({type(exc).__name__}); içerik güvenli biçimde reddedildi.")
agent_ids = tuple(AGENT_PROFILES)
selected_agent = st.selectbox(
    "Destek ajanı", options=agent_ids,
    format_func=lambda key: AGENT_PROFILES[key][0], key="organism_agent_role",
    help="Ajan profilleri yalnızca kullanıcının başlattığı yanıta yön verir; araç izni veya kendi kendine işlem yetkisi vermez. Açıkça kaydedilmiş notlar ortak hafıza olarak bağlamda kullanılır.",
)
st.caption("Ajanlar yalnızca açıkça kaydedilen notları bağlam olarak kullanır. Gönderilen bulut sohbetleri özel arşivde saklanır; sohbetler model ağırlıklarını eğitmez.")
learning_query = st.text_area("Asistana sor" if CLOUD_MODE else "Yerel asistana sor", max_chars=4000, key="learning_query")
ask_local_clicked = st.button("Groq'a sor" if CLOUD_MODE and selected_provider == "groq" else "Yanıt üret" if CLOUD_MODE else "Yerel Qwen'e sor", key="local_learning_chat", disabled=CLOUD_MODE and not groq_configured)
if ask_local_clicked:
    try:
        relevant = retrieve_memories(OUTPUT_DIR, learning_query)
        agent_prompt = learning_query
        if selected_provider != "groq":
            agent_prompt = profile_prompt(selected_agent) + "\n\nKullanıcının isteği:\n" + learning_query
        response = generate(augment_with_memory(agent_prompt, relevant), selected_provider,
                           model=selected_model,
                           system_prompt=profile_prompt(selected_agent) if selected_provider == "groq" else None)
        st.session_state["local_learning_answer"] = response.get("text", "")
        st.session_state["local_learning_context_count"] = len(relevant)
        if CLOUD_MODE:
            chat_path = OUTPUT_DIR / "chat_history.jsonl"
            with chat_path.open("a", encoding="utf-8") as history_file:
                history_file.write(json.dumps({
                    "id": uuid4().hex,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "agent": selected_agent,
                    "provider": response.get("provider", "groq"),
                    "model": selected_model,
                    "question": learning_query,
                    "answer": response.get("text", ""),
                    "saved_note_count": len(relevant),
                }, ensure_ascii=False, allow_nan=False) + "\n")
        st.session_state["local_learning_provider"] = response.get("provider", "ollama")
    except (ProviderError, OSError, ValueError, RuntimeError) as exc:
        if isinstance(exc, ProviderError):
            # ProviderError messages contain fixed, sanitized categories/status codes only.
            detail = str(exc)[:180]
        else:
            detail = type(exc).__name__
        st.error(f"Model yanıt vermedi ({detail}); kaydedilmiş hafıza korunuyor.")
if st.session_state.get("local_learning_answer"):
    st.markdown("**Ajan yanıtı**")
    st.write(st.session_state["local_learning_answer"])
    st.caption(f"Model: {st.session_state.get('local_learning_provider', 'ollama')} · eklenen kayıtlı not: {st.session_state.get('local_learning_context_count', 0)}")
with st.expander("Hesabımda saklanan kalıcı notlar" if CLOUD_MODE else "Bu bilgisayarda saklanan hafıza notları"):
    memory_rows = list_memories(OUTPUT_DIR)
    if memory_rows:
        st.dataframe([{"Başlık": row["topic"], "Not": row["content"],
                       "Köken": "kullanıcının açıkça kaydettiği"} for row in memory_rows],
                     width="stretch", hide_index=True)
    else:
        st.info("Henüz kaydedilmiş not yok.")

st.header("Bilimsel literatür kataloğu")
st.caption("OpenAlex'ten en fazla 5 bibliyografik kayıt getirir ve kaynak kökeniyle hesaba özel kalıcı arşive kaydeder. Katalog kaydı, makalenin içeriğini veya iddialarını doğrulamaz.")
literature_query = st.text_input("Araştırma konusu", value="digital evolution Avida", max_chars=200)
if st.button("Literatürde ara ve kaydet", key="search_literature"):
    try:
        with st.spinner("OpenAlex kataloğunda aranıyor…"):
            records = search_openalex(literature_query, per_page=5)
            saved_count = save_records(OUTPUT_DIR, literature_query, records)
        st.session_state["literature_search_message"] = f"{len(records)} kayıt bulundu; {saved_count} kayıt eklendi veya güncellendi."
    except (OSError, ValueError, TimeoutError) as exc:
        st.session_state["literature_search_message"] = f"Arama tamamlanamadı ({type(exc).__name__}); simülasyon kayıtları etkilenmedi."
if st.session_state.get("literature_search_message"):
    st.info(st.session_state["literature_search_message"])
all_literature_records = list_records(OUTPUT_DIR)
literature_records = [item for item in all_literature_records
                      if item.get("work_type") == "article"
                      and item.get("source_type") in {"journal", "conference"}
                      and item.get("is_retracted") is False]
if literature_records:
    st.dataframe([{
        "Başlık": item["title"], "Yıl": item["publication_year"],
        "Yazarlar": ", ".join(item["authors"][:4]), "Dergi": item["venue"],
        "Tür": item["work_type"], "Yayın yeri türü": item["source_type"],
        "DOI": item["doi"], "OpenAlex": item["openalex_id"],
        "Durum": "Katalog metaverisi; bağımsız doğrulanmadı",
    } for item in literature_records], width="stretch")
    for item in literature_records[:10]:
        link = item["doi"] or item["landing_page_url"] or item["openalex_id"]
        st.markdown(f"[{item['title']}]({link}) · {item['publication_year'] or 'Yıl yok'} · kaynak: OpenAlex")
elif all_literature_records:
    st.info("Kayıtlı kaynakların makale türü henüz süzülmedi. Güncel arama, yalnızca OpenAlex'te makale türünde ve geri çekilmiş olarak işaretlenmemiş sonuçları gösterir.")

worker_status_path = OUTPUT_DIR / "continuous_research_status.json"
if worker_status_path.exists():
    try:
        worker_status = json.loads(worker_status_path.read_text(encoding="utf-8"))
        if worker_status.get("status") == "running":
            st.success(f"Sürekli yerel araştırma çalışıyor · tamamlanan döngü: {worker_status.get('last_completed_cycle', 0)}")
            if worker_status.get("research_scope"):
                st.caption(f"Son/aktif deney: {worker_status['research_scope']}. Yalnızca dijital simülasyon.")
            if worker_status.get("last_study_type") == "environment_shift" and worker_status.get("last_report_path"):
                try:
                    shift_report = json.loads(Path(worker_status["last_report_path"]).read_text(encoding="utf-8"))
                    st.dataframe(shift_report["results"], width="stretch", hide_index=True)
                    st.caption("Bu uyum ölçümleri sanal ortamdan gelir; model ağırlıkları veya gerçek canlılar üzerinde öğrenme göstermez.")
                except (OSError, ValueError, KeyError, TypeError):
                    st.info("Son çevre değişimi raporu okunamadı; ham rapor dosyası korunuyor.")
            summary_path = OUTPUT_DIR / "research_summary.json"
            if summary_path.exists():
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                st.caption(f"Otomatik karşılaştırma: {summary.get('study_count', 0)} çalışma, {summary.get('condition_count', 0)} koşul")
                if summary.get("highest_observed_simulation_condition"):
                    top = summary["highest_observed_simulation_condition"]
                    st.caption("Bu simülasyonda en yüksek ortalama nüfus gözlenen koşul: "
                               f"kapasite {top['capacity']}, kaynak {top['resource_per_tick']}, "
                               f"mutasyon {top['mutation_rate']} — gerçek dünya sonucu değildir.")
        elif worker_status.get("status") == "running_with_error":
            st.warning(f"Araştırma süreci açık; son deneyde hata oluştu ({worker_status.get('last_error_type', 'bilinmeyen hata')}). Yeniden deneyecek.")
        else:
            st.info(f"Sürekli araştırma durumu: {worker_status.get('status', 'bilinmiyor')} · tamamlanan döngü: {worker_status.get('last_completed_cycle', 0)}")
    except (OSError, ValueError, AttributeError):
        st.info("Araştırma durumu okunamadı; kayıtlı deneyler korunuyor.")

steps = st.slider("Simülasyon adımı", min_value=0, max_value=100, value=10)
energy = st.number_input("Başlangıç enerjisi", min_value=0, max_value=100000, value=40, step=1)
materials = st.number_input("Başlangıç malzemesi", min_value=0, max_value=100000, value=12, step=1)

if st.button("Simülasyonu çalıştır", type="primary"):
    st.session_state["organism_result"] = run_shared_world(steps=steps, energy=int(energy), materials=int(materials))
    if CLOUD_MODE:
        (OUTPUT_DIR / "simulation_result.json").write_text(
            json.dumps(st.session_state["organism_result"], ensure_ascii=False, allow_nan=False),
            encoding="utf-8",
        )
if CLOUD_MODE and "organism_result" not in st.session_state:
    try:
        st.session_state["organism_result"] = json.loads(
            (OUTPUT_DIR / "simulation_result.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError):
        pass

if "organism_result" in st.session_state:
    result = st.session_state["organism_result"]
    a, b, c = st.columns(3)
    a.metric("Sanal robot", result["robots"])
    b.metric("Sanal organizma", result["organisms"])
    c.metric("Başarılı sanal rota", result["successful_routes"])
    st.subheader("Kaynakların adımlara göre değişimi")
    if result["history"]:
        st.line_chart(result["history"], x="tick", y=["energy_left", "materials_left"])
        st.dataframe(result["history"], width="stretch")
    else:
        st.info("Sıfır adım seçildi; işlem yapılmadı.")
    st.download_button("JSON raporunu indir", data=json.dumps(result, ensure_ascii=False, indent=2), file_name="organism_lab_report.json", mime="application/json")

st.divider()
st.header("Genom çoğaltma araştırması")
st.caption("30 eşlenmiş tohum × 100 adım × 5 kaynak düzeyi. COPY_REST ve DIVIDE komutlarını yürüten genom, aynı genomun bölünmesi kapalı kontrolüyle karşılaştırılır; yavru genomlarda %2 komut mutasyonu uygulanır. Ölçümler yalnızca bu dijital simülasyona aittir.")
if st.button("Araştırma kampanyasını çalıştır", key="run_genome_study_v2", type="primary"):
    with st.spinner("Sanal genomları çalıştıran eşlenmiş deneyler yürütülüyor ve kaydediliyor…"):
        campaign = run_study(seeds=tuple(range(30)), steps=100,
                             resource_levels=(0, 2, 5, 10, 20))
        commentary = {"status": "not_requested", "text": ""}
        saved = save_study(campaign, OUTPUT_DIR,
                           model_commentary=commentary)
    if CLOUD_MODE:
        (OUTPUT_DIR / "genome_campaign_latest.json").write_text(
            json.dumps(campaign, ensure_ascii=False, allow_nan=False), encoding="utf-8"
        )
    st.session_state["genome_campaign_v2"] = campaign
    st.session_state["genome_commentary_v2"] = commentary
    st.session_state["genome_saved_v2"] = saved

if "genome_campaign_v2" in st.session_state:
    campaign = st.session_state["genome_campaign_v2"]
    st.dataframe(campaign["results"], width="stretch")
    commentary = st.session_state["genome_commentary_v2"]
    st.info("Deney ölçümleri doğrudan simülasyondan hesaplandı. Bu kampanyada yerel model kontrolü kullanılmadı.")
    saved = st.session_state["genome_saved_v2"]
    st.success(f"Kayıt tamamlandı · çalışma {saved['study_id']} · JSON, CSV ve SQLite")
    st.download_button("Deney verisini JSON indir",
                       data=json.dumps({**campaign, "model_commentary": commentary}, ensure_ascii=False, indent=2),
                       file_name="reproduction-study.json", mime="application/json",
                       key="download_reproduction_json")

st.subheader("Çevre değişimine uyum deneyi")
st.caption("Yeni deney: TASK_A ortamında başlayan sanal genomlar, 40. adımdan sonra TASK_B ortamına geçer. Mutasyonlu soy, aynı tohumlarda mutasyonsuz kontrolle karşılaştırılır. Bu simüle edilmiş evrimsel seçilimdir; yapay zekâ modelinin kendi ağırlıklarını öğrenmesi değildir.")
if st.button("Uyum deneyini çalıştır (30 eşlenmiş tohum)", key="run_environment_shift"):
    try:
        adaptation = run_adaptation_study()
        path = save_adaptation_study(adaptation, OUTPUT_DIR / "environment-shift-study.json")
        st.session_state["environment_shift_report"] = adaptation
        st.session_state["environment_shift_path"] = str(path)
    except (OSError, ValueError, RuntimeError) as exc:
        st.error(f"Uyum deneyi tamamlanamadı ({type(exc).__name__}); mevcut kayıtlar korunuyor.")
if CLOUD_MODE and "genome_campaign_v2" not in st.session_state:
    try:
        st.session_state["genome_campaign_v2"] = json.loads(
            (OUTPUT_DIR / "genome_campaign_latest.json").read_text(encoding="utf-8")
        )
        st.session_state["genome_saved_v2"] = {"study_id": "restored"}
        st.session_state["genome_commentary_v2"] = {"status": "not_requested", "text": ""}
    except (OSError, ValueError, TypeError):
        pass

if CLOUD_MODE and "environment_shift_report" not in st.session_state:
    try:
        st.session_state["environment_shift_report"] = json.loads(
            (OUTPUT_DIR / "environment-shift-study.json").read_text(encoding="utf-8")
        )
        st.session_state["environment_shift_path"] = str(OUTPUT_DIR / "environment-shift-study.json")
    except (OSError, ValueError, TypeError):
        pass

if "environment_shift_report" in st.session_state:
    adaptation = st.session_state["environment_shift_report"]
    st.dataframe(adaptation["results"], width="stretch", hide_index=True)
    st.download_button("Uyum deneyi raporunu indir (JSON)",
                       data=json.dumps(adaptation, ensure_ascii=False, indent=2),
                       file_name="environment-shift-study.json", mime="application/json",
                       key="download_environment_shift")
    st.caption("Kalıcı kayıt: " + st.session_state["environment_shift_path"])

with st.expander("Kayıtlı araştırmaların otomatik özeti"):
    summary_path = OUTPUT_DIR / "research_summary.json"
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            st.caption("Bu karşılaştırma yalnızca yerel dijital simülasyon ölçümlerini toplar; gerçek canlılar veya robotlar hakkında doğrulama değildir.")
            st.write(f"Çalışma sayısı: {summary.get('study_count', 0)} · koşul sayısı: {summary.get('condition_count', 0)}")
            if summary.get("conditions"):
                st.dataframe(summary["conditions"], width="stretch")
        except (OSError, ValueError, TypeError):
            st.info("Araştırma özeti okunamadı; ham kayıtlar korunuyor.")
    else:
        st.info("Sürekli araştırma ilk özetini oluşturduğunda burada görünür.")

if CLOUD_MODE:
    try:
        _snapshot_data = pack_directory(OUTPUT_DIR)
        _snapshot_digest = hashlib.sha256(_snapshot_data).hexdigest()
        if _snapshot_digest != st.session_state.get("organism_lab_archive_baseline"):
            try:
                _archive_baseline = _archive.save(
                    _snapshot_data,
                    expected_digest=st.session_state.get("organism_lab_archive_baseline"),
                )
                st.session_state["organism_lab_archive_baseline"] = _archive_baseline
                st.session_state.pop("organism_lab_archive_conflict", None)
                st.success("Laboratuvar verileri kalıcı arşive kaydedildi.")
            except PersistenceConflict:
                st.session_state["organism_lab_archive_conflict"] = True
                st.error("Başka bir oturum arşivi güncelledi. Bu oturumdaki veriyi indirin; üzerine yazılmadı.")
        st.download_button(
            "Kalıcı laboratuvar arşivini yedekle",
            data=_snapshot_data,
            file_name="organism-lab-backup.tar.gz",
            mime="application/gzip",
            key="organism_lab_backup_download",
        )
        _restore_upload = st.file_uploader(
            "Önceden indirdiğin laboratuvar yedeğini geri yükle",
            type=["gz"],
            key="organism_lab_restore_upload",
        )
        if _restore_upload is not None and st.button("Yedeği geri yükle", key="organism_lab_restore"):
            try:
                unpack_directory(_restore_upload.getvalue(), OUTPUT_DIR)
                _new_backup = pack_directory(OUTPUT_DIR)
                _new_digest = _archive.save(
                    _new_backup,
                    expected_digest=st.session_state.get("organism_lab_archive_baseline"),
                )
                st.session_state["organism_lab_archive_baseline"] = _new_digest
                st.session_state.pop("organism_lab_archive_conflict", None)
                st.success("Yedek doğrulandı ve kalıcı arşive geri yüklendi.")
            except (OSError, ValueError, RuntimeError):
                st.error("Yedek doğrulanamadı; mevcut laboratuvar arşivi değiştirilmedi.")
    except Exception as exc:
        st.error(f"Kalıcı arşiv işlemi tamamlanamadı ({type(exc).__name__}); uygulama içeriği güvenli biçimde gizlendi.")


