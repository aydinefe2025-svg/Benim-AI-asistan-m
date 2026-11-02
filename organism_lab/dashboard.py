"""Optional local Streamlit dashboard for the offline simulation.

Run: streamlit run organism_lab/dashboard.py
No external services, credentials, or production app changes are required.
"""
from pathlib import Path
import json
import sys

# Streamlit launches this file directly; ensure repository imports resolve.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from organism_lab.shared_world import run_shared_world
from organism_lab.reproduction_study import run_study, save_study, summarize_with_local_model

st.set_page_config(page_title="Organizma Laboratuvarı", layout="wide")
st.title("Organizma Laboratuvarı")
st.caption("Yalnızca deterministik dijital simülasyon. Fiziksel robot veya biyolojik organizma kontrolü içermez.")

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
if st.button("Araştırma kampanyasını çalıştır", key="run_reproduction_study", type="primary"):
    with st.spinner("Sanal genomları çalıştıran eşlenmiş deneyler yürütülüyor; sonuçlar ve yerel model kontrolü kaydediliyor…"):
        campaign = run_study(seeds=tuple(range(30)), steps=100,
                             resource_levels=(0, 2, 5, 10, 20))
        commentary = summarize_with_local_model(campaign)
        saved = save_study(campaign, Path.cwd() / "organism_lab_output",
                           model_commentary=commentary)
    st.session_state["reproduction_campaign"] = campaign
    st.session_state["reproduction_commentary"] = commentary
    st.session_state["reproduction_saved"] = saved

if "reproduction_campaign" in st.session_state:
    campaign = st.session_state["reproduction_campaign"]
    st.dataframe(campaign["results"], width="stretch")
    commentary = st.session_state["reproduction_commentary"]
    if commentary["status"] == "metric_consistent":
        st.info("Yerel Qwen'in yapılandırılmış ölçüm kontrolü hesaplanan değerlerle eşleşti. Sonuç tablosu doğrudan simülasyon hesaplamalarından gelir.")
    elif commentary["status"] == "rejected_inconsistent":
        st.error("Yerel modelin ölçüm kontrolü hesaplamalarla çelişti ve gösterilmeden reddedildi. Deney ölçümleri kaydedildi.")
    else:
        st.info("Yerel model yorumu alınamadı; hesaplanan deney sonuçları yine de kaydedildi.")
    saved = st.session_state["reproduction_saved"]
    st.success(f"Kayıt tamamlandı · çalışma {saved['study_id']} · JSON, CSV ve SQLite")
    st.download_button("Deney verisini JSON indir",
                       data=json.dumps({**campaign, "model_commentary": commentary}, ensure_ascii=False, indent=2),
                       file_name="reproduction-study.json", mime="application/json",
                       key="download_reproduction_json")
