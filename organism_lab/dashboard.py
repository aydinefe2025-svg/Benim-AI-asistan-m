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
from organism_lab.reproduction_study import run_study, save_study
from organism_lab.study_verifier import verify_saved_study

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
if st.button("Araştırma kampanyasını çalıştır", key="run_genome_study_v2", type="primary"):
    for key in ("genome_campaign_v2", "genome_commentary_v2", "genome_saved_v2",
                "genome_verified_receipt_v2"):
        st.session_state.pop(key, None)
    try:
        with st.spinner("Sanal genomlar çalıştırılıyor; kayıtlar geri okunup yeniden hesaplanıyor…"):
            campaign = run_study(seeds=tuple(range(30)), steps=100,
                                 resource_levels=(0, 2, 5, 10, 20))
            commentary = {"status": "not_requested", "text": ""}
            saved = save_study(campaign, Path.cwd() / "organism_lab_output",
                               model_commentary=commentary)
            receipt = verify_saved_study(saved)
    except (OSError, ValueError) as exc:
        st.error(f"Kayıt doğrulanamadı. Başarılı sayılmadı: {type(exc).__name__}")
    else:
        st.session_state["genome_campaign_v2"] = campaign
        st.session_state["genome_commentary_v2"] = commentary
        st.session_state["genome_saved_v2"] = saved
        st.session_state["genome_verified_receipt_v2"] = receipt

if "genome_campaign_v2" in st.session_state:
    campaign = st.session_state["genome_campaign_v2"]
    st.dataframe(campaign["results"], width="stretch")
    st.info("Deney ölçümleri doğrudan simülasyondan hesaplandı. Bu kampanyada yerel model kontrolü kullanılmadı.")
    saved = st.session_state["genome_saved_v2"]
    receipt = st.session_state["genome_verified_receipt_v2"]
    st.success(f"Kayıt tamamlandı ve geri okundu · çalışma {saved['study_id']} · JSON, CSV ve SQLite")
    st.caption(f"Bağımsız sayısal yeniden hesaplama doğrulandı · {receipt['observations']} gözlem · SHA-256 {receipt['json_sha256'][:16]}…")
    st.download_button("Deney verisini JSON indir",
                       data=json.dumps({**campaign, "model_commentary": st.session_state["genome_commentary_v2"]}, ensure_ascii=False, indent=2),
                       file_name="reproduction-study.json", mime="application/json",
                       key="download_reproduction_json")
