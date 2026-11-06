"""CANO's explicitly triggered, bounded digital-organism lab UI.

No physical robotics, biological experiments, LLM calls, network writes, or
server-side persistence. The user can download exact results as JSON.
"""
from __future__ import annotations

import hashlib
import json

from organism_lab.reproduction_study import run_study
from organism_lab.shared_world import run_shared_world


def json_export(document):
    return (json.dumps(document, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")



def explain_campaign(report):
    """Explain computed study metrics in plain Turkish without another model call."""
    try:
        design = report["design"]
        results = report["results"]
        observations = report["observations"]
        if not isinstance(results, list) or not results or not isinstance(observations, list):
            raise ValueError
        best = max(results, key=lambda row: row["paired_population_difference"]["mean"])
        difference = best["paired_population_difference"]
        low, high, mean = difference["ci95_low"], difference["ci95_high"], difference["mean"]
        numbers = (mean, low, high)
        if any(type(value) not in (int, float) for value in numbers):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ValueError("Study report has no valid computed results") from None

    includes_zero = low <= 0 <= high
    uncertainty = (
        "Bu yaklaşık aralık sıfırı içeriyor; seçilen tohumlarda kontrol ile fark net değil."
        if includes_zero else
        "Bu yaklaşık aralık sıfırı içermiyor; fark seçilen simülasyon tohumlarında tutarlı görünüyor."
    )
    return (
        f"**Ne denendi?** {len(design['seeds'])} aynı başlangıç tohumu, "
        f"{design['steps']} sanal adım ve {len(design['resource_levels_per_tick'])} kaynak düzeyi kullanıldı. "
        "Kopyalanıp bölünebilen dijital genom, aynı koşullarda bölünmesi kapatılmış kontrolle karşılaştırıldı.\\n\\n"
        f"**Ne bulundu?** En büyük ortalama fark, adım başına "
        f"{best['resource_per_tick']} sanal kaynak düzeyinde {mean:.2f} organizmaydı "
        f"(yaklaşık %95 aralık {low:.2f} ile {high:.2f}; {best['paired_seeds']} eşlenmiş tohum). "
        f"{uncertainty}\\n\\n"
        f"**Bu ne anlama geliyor?** Bu ayarlarda çoğalma kuralı, simülatör içindeki nüfus sonucunu "
        "kontrole göre değiştirdi. Rapor ve her tohumun ham sonucu JSON dosyasına eklenmiştir. "
        "Bu sonuç yalnızca dijital model içindir; gerçek hücre, doğa veya robot davranışını kanıtlamaz."
    )


def run_checked_campaign(*, seeds=10, steps=40):
    """Execute and independently replay a bounded, paired simulation."""
    if type(seeds) is not int or not 2 <= seeds <= 10:
        raise ValueError("Seed count outside the safe web budget")
    if type(steps) is not int or not 1 <= steps <= 100:
        raise ValueError("Step count outside the safe web budget")
    parameters = {"seeds": tuple(range(seeds)), "steps": steps,
                  "resource_levels": (0, 2, 5, 10, 20)}
    report = run_study(**parameters)
    if report != run_study(**parameters):
        raise RuntimeError("Independent replay did not match")
    blob = json_export(report)
    return {"report": report, "json": blob,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "observations": len(report["observations"])}


def render_organism_lab_panel(st):
    """Render only inside app.py, after its existing authentication gate."""
    with st.sidebar.expander("🧬 Organizmalar Laboratuvarı", expanded=False):
        st.caption(
            "Yalnızca sınırlı dijital simülasyon. Gerçek hücre veya robot çalıştırmaz; "
            "kendiliğinden yeni ajan oluşturmaz ve model API'si kullanmaz."
        )
        steps = st.slider("Sanal dünya adımları", 0, 50, 10, key="cano_organism_world_steps")
        energy = st.number_input(
            "Başlangıç enerjisi", min_value=0, max_value=1000, value=40, step=1,
            key="cano_organism_world_energy")
        materials = st.number_input(
            "Başlangıç malzemesi", min_value=0, max_value=1000, value=12, step=1,
            key="cano_organism_world_materials")
        if st.button("Dijital dünyayı çalıştır", key="cano_organism_world_run"):
            try:
                result = run_shared_world(
                    steps=int(steps), energy=int(energy), materials=int(materials))
                st.session_state["cano_organism_world_result"] = result
            except (ValueError, RuntimeError):
                st.session_state.pop("cano_organism_world_result", None)
                st.error("Dijital dünya hesaplaması doğrulanamadı.")
        result = st.session_state.get("cano_organism_world_result")
        if result is not None:
            st.metric("Sanal robot", result["robots"])
            st.metric("Sanal organizma", result["organisms"])
            st.metric("Başarılı sanal rota", result["successful_routes"])
            st.download_button(
                "Sanal dünya JSON indir", data=json_export(result),
                file_name="cano-dijital-dunya.json", mime="application/json",
                key="cano_organism_world_download")

        st.divider()
        st.caption("Kontrollü genom deneyi: 10 eşlenmiş tohum × 40 adım × 5 kaynak seviyesi.")
        if st.button("Genom karşılaştırmasını çalıştır", key="cano_organism_campaign_run"):
            st.session_state.pop("cano_organism_campaign_result", None)
            try:
                st.session_state["cano_organism_campaign_result"] = run_checked_campaign()
            except (ValueError, RuntimeError):
                st.error("Genom deneyi yeniden hesaplamayla doğrulanamadı.")
        saved = st.session_state.get("cano_organism_campaign_result")
        if saved is not None:
            st.success(
                f"{saved['observations']} dijital gözlem yeniden hesaplanarak doğrulandı.")
            st.markdown(explain_campaign(saved["report"]))
            st.dataframe(saved["report"]["results"], hide_index=True)
            st.caption("JSON SHA-256: " + saved["sha256"])
            st.download_button(
                "Deney kanıtını JSON indir", data=saved["json"],
                file_name="cano-genom-karsilastirma.json",
                mime="application/json", key="cano_organism_campaign_download")
        st.warning(
            "Sonuçlar yalnızca bu tarayıcı oturumunda tutulur. "
            "Sunucunun geçici diskine veya PostgreSQL'e kaydedilmez; "
            "kalıcı arşiv için JSON dosyasını indirin."
        )
