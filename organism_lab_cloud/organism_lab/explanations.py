"""Plain-language, deterministic explanations for computed lab reports.

Text here is derived only from recorded simulator metrics. It must never imply
that a digital simulation was a physical experiment or biological evidence.
"""


def explain_shared_world(result):
    steps = len(result.get("history", []))
    robots = int(result.get("robots", 0))
    organisms = int(result.get("organisms", 0))
    births = int(result.get("births", 0))
    routes = int(result.get("successful_routes", 0))
    energy = int(result.get("energy_left", 0))
    materials = int(result.get("materials_left", 0))
    if steps == 0:
        finding = "0 adım seçildiği için sanal dünyada hiçbir işlem yapılmadı."
    else:
        finding = (
            f"{steps} adım sonunda {robots} sanal robot kuruldu, nüfus "
            f"{organisms} oldu ({births} yeni doğum) ve {routes} rota denemesi "
            f"başarılı sayıldı. {energy} enerji ve {materials} malzeme kaldı."
        )
    return {
        "what_was_tested": "Sınırlı enerji ve malzeme robot kurma, sanal doğum ve rota bulma işlerine yetiyor mu?",
        "finding": finding,
        "meaning": "Bu sonuç, yalnızca bu ayarlarla çalışan basit sanal dünyanın kaynak hesabını anlatır.",
        "limits": "Gerçek robot, hücre veya canlı üzerinde deney yapılmadı; bu simülasyon gerçek dünyadaki davranışı kanıtlamaz.",
    }


def explain_reproduction_study(report):
    lines = []
    for row in report.get("results", []):
        difference = row.get("paired_population_difference", {})
        mean = float(difference.get("mean", 0))
        low, high = difference.get("ci95_low"), difference.get("ci95_high")
        level = row.get("resource_per_tick", "?")
        if low is None or high is None:
            evidence = "belirsizlik aralığı hesaplanmadı"
        elif low <= 0 <= high:
            evidence = "%95 yaklaşık aralığı sıfırı kapsıyor; bu koşulda fark net değil"
        elif low > 0:
            evidence = "%95 yaklaşık aralığının tamamı sıfırın üstünde; simülasyonda çoğalma lehine fark var"
        else:
            evidence = "%95 yaklaşık aralığının tamamı sıfırın altında; simülasyonda kontrol lehine fark var"
        lines.append(
            f"Adım başına {level} kaynak: çoğalma açık ve kapalı grupların ortalama son nüfus farkı "
            f"{mean:.2f}; {evidence}."
        )
    design = report.get("design", {})
    seeds = len(design.get("seeds", []))
    return {
        "what_was_tested": "Aynı sanal genom ve kaynak düzeyi, aynı rastgele tohumlarla iki grupta çalıştırıldı: bir grupta bölünme açıktı, kontrol grubunda kapalıydı.",
        "finding": " ".join(lines) if lines else "Raporda yorumlanabilir sonuç satırı bulunamadı.",
        "meaning": f"Bu karşılaştırma, belirtilen simülasyon kurallarında bölünme özelliğinin nüfusa etkisini ölçer. {seeds} eşlenmiş tohum kullanıldı.",
        "limits": "Aralıklar yalnızca bu sanal model ve seçilen tohumlardaki değişkenliği özetler; biyolojik deney veya canlılar hakkında kanıt değildir.",
    }


def explain_adaptation_study(report):
    rows = {row.get("arm"): row for row in report.get("results", [])}
    mutation = rows.get("mutation", {})
    control = rows.get("no_mutation", {})
    mut_share = float(mutation.get("final_task_b_share_mean", 0))
    control_share = float(control.get("final_task_b_share_mean", 0))
    delta = mut_share - control_share
    direction = "yüksek" if delta > 0 else "düşük" if delta < 0 else "aynı"
    pct = abs(delta) * 100
    shift = report.get("design", {}).get("shift_tick", "?")
    return {
        "what_was_tested": f"Sanal ortam {shift}. adımda A görevinden B görevine geçirildi. Mutasyonlu grup, aynı tohumlardaki mutasyonsuz grupla karşılaştırıldı.",
        "finding": (
            f"Son adımda TASK_B komutunu taşıyanların ortalama payı mutasyonlu grupta "
            f"%{mut_share * 100:.1f}, kontrol grubunda %{control_share * 100:.1f} idi. "
            f"Mutasyonlu grupta fark {direction} ({pct:.1f} yüzde puan)."
        ),
        "meaning": "Bu, sadece simülatörde tanımlanan görev ve ödül kuralları altında görülen farktır; simülatör sonucu kodla hesaplanmıştır.",
        "limits": "Bu sonuç gerçek canlıların uyum sağladığını veya yapay zekânın model ağırlıklarını öğrendiğini göstermez; yalnızca sanal genom değişimini ölçer.",
    }


def render_explanation(st, explanation, *, key):
    """Render an accessible result card with consistent wording."""
    with st.expander("Sonucu sade dille açıkla", key=key):
        st.markdown(f"**Ne denendi?** {explanation['what_was_tested']}")
        st.markdown(f"**Ne bulundu?** {explanation['finding']}")
        st.markdown(f"**Bu ne anlama geliyor?** {explanation['meaning']}")
        st.markdown(f"**Sınırı ne?** {explanation['limits']}")

