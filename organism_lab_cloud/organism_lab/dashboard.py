"""Streamlit dashboard for the digital organism lab (local or hosted demo)."""
from pathlib import Path
import json
import os
import sys

# Streamlit launches this file directly; ensure repository imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from organism_lab.shared_world import run_shared_world
from organism_lab.reproduction_study import run_study, save_study
from organism_lab.adaptation_study import run_adaptation_study, save_adaptation_study
from organism_lab.literature_search import list_records, save_records, search_openalex
from organism_lab.persistent_memory import (augment_with_memory, list_memories,
                                            retrieve_memories, save_memory)
from organism_lab.providers import ProviderError, generate, trained_local_ready
from organism_lab.cloud_runtime import default_provider, session_output_dir

CLOUD_MODE = os.environ.get("ORGANISM_LAB_CLOUD_MODE", "").strip() == "1"
if CLOUD_MODE:
    OUTPUT_DIR = session_output_dir(
        os.environ.get("ORGANISM_LAB_OUTPUT_DIR", "/tmp/organism-lab-sessions"),
        st.session_state,
    )
else:
    OUTPUT_DIR = Path(os.environ.get(
        "ORGANISM_LAB_OUTPUT_DIR",
        Path(__file__).resolve().parents[3] / "organism_lab_output",
    )).resolve()

st.set_page_config(page_title="Organizma Laboratuvarı", layout="wide")
st.title("Organizma Laboratuvarı")
st.caption("Yalnızca dijital simülasyon. Fiziksel robot veya biyolojik organizma kontrolü içermez.")
if CLOUD_MODE:
    st.warning(
        "Bulut demo modu: her tarayıcı oturumu ayrı geçici depolama kullanır. "
        "Render yeniden başlatılır veya dağıtım yapılırsa notlar ve deney dosyaları silinebilir; "
        "önemli sonuçları indirin. Bu örnekte giriş hesabı ve kalıcı arşiv etkin değildir. "
        "Yerel Ollama/LoRA modeli bu sunucuda çalışmaz."
    )

st.header("Araştırma asistanı ve oturum notları" if CLOUD_MODE else "Yerel asistan ve kalıcı hafıza")
st.caption(
    "Bu tarayıcı oturumunda açıkça eklenen notlar geçici SQLite dosyasında tutulur. "
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
elif CLOUD_MODE:
    if os.environ.get("GROQ_API_KEY", "").strip():
        st.info("Bulut sohbeti Groq üzerinden çalışır; gönderdiğin soru ve kullanılan açıkça kaydedilmiş notlar sağlayıcıya iletilir.")
        selected_provider = st.selectbox(
            "Sohbet modeli", options=["groq"], format_func=lambda _: "Groq (bulut)",
            key="assistant_model_choice",
        )
    else:
        st.info("Bulut sohbet modeli yapılandırılmamış. Dijital simülasyon ve literatür kataloğu kullanılabilir; sohbet için sunucuda güvenli GROQ_API_KEY gerekir.")
        selected_provider = default_provider(cloud_mode=True)
else:
    st.info("Şu an Ollama temel modeli kullanılıyor; bu bilgisayarda eğitilmiş bir adaptör etkin değil. Kaydedilen notlar yanıta bağlam olarak eklenir, model ağırlıklarını değiştirmez.")
    selected_provider = "ollama"
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
save_memory_clicked = st.button("Notu oturuma kaydet" if CLOUD_MODE else "Notu kalıcı hafızaya kaydet", key="save_assistant_memory")
if save_memory_clicked:
    try:
        note = save_memory(OUTPUT_DIR, memory_topic, memory_content)
        location = "yalnızca bu oturumda" if CLOUD_MODE else "yalnızca yerel bilgisayarda"
        st.success(f"Not kaydedildi · #{note['id']} · {location}")
    except (OSError, ValueError) as exc:
        st.error(f"Not kaydedilemedi ({type(exc).__name__}); içerik güvenli biçimde reddedildi.")
learning_query = st.text_area("Asistana sor" if CLOUD_MODE else "Yerel asistana sor", max_chars=4000, key="learning_query")
ask_local_clicked = st.button("Groq'a sor" if CLOUD_MODE and selected_provider == "groq" else "Yanıt üret" if CLOUD_MODE else "Yerel Qwen'e sor", key="local_learning_chat", disabled=CLOUD_MODE and selected_provider == "offline")
if ask_local_clicked:
    try:
        relevant = retrieve_memories(OUTPUT_DIR, learning_query)
        response = generate(augment_with_memory(learning_query, relevant), selected_provider)
        st.session_state["local_learning_answer"] = response.get("text", "")
        st.session_state["local_learning_context_count"] = len(relevant)
        st.session_state["local_learning_provider"] = response.get("provider", "ollama")
    except (ProviderError, OSError, ValueError, RuntimeError) as exc:
        st.error(f"Model yanıt vermedi ({type(exc).__name__}); kaydedilmiş hafıza korunuyor.")
if st.session_state.get("local_learning_answer"):
    st.markdown("**Yerel modelin yanıtı**")
    st.write(st.session_state["local_learning_answer"])
    st.caption(f"Model: {st.session_state.get('local_learning_provider', 'ollama')} · eklenen kayıtlı not: {st.session_state.get('local_learning_context_count', 0)}")
with st.expander("Bu oturumdaki hafıza notları" if CLOUD_MODE else "Bu bilgisayarda saklanan hafıza notları"):
    memory_rows = list_memories(OUTPUT_DIR)
    if memory_rows:
        st.dataframe([{"Başlık": row["topic"], "Not": row["content"],
                       "Köken": "kullanıcının açıkça kaydettiği"} for row in memory_rows],
                     width="stretch", hide_index=True)
    else:
        st.info("Henüz kaydedilmiş not yok.")

st.header("Bilimsel literatür kataloğu")
st.caption("OpenAlex'ten en fazla 5 bibliyografik kayıt getirir ve kaynak kökeniyle kaydeder. Bulut demosunda kayıtlar geçici oturum depolamasındadır. Katalog kaydı, makalenin içeriğini veya iddialarını doğrulamaz.")
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

