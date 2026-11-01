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
