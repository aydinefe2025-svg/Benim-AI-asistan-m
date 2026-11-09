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
    no_reproduction = rows.get("no_reproduction")
    mut_share = float(mutation.get("final_task_b_share_mean", 0))
    control_share = float(control.get("final_task_b_share_mean", 0))
    delta = mut_share - control_share
    direction = "yüksek" if delta > 0 else "düşük" if delta < 0 else "aynı"
    pct = abs(delta) * 100
    shift = report.get("design", {}).get("shift_tick", "?")
    controls_text = (" mutasyonsuz ve çoğalmasız kontrollerle"
                     if no_reproduction else " mutasyonsuz kontrolle")
    finding = (
        f"Son adımda TASK_B komutunu taşıyanların ortalama payı mutasyonlu grupta "
        f"%{mut_share * 100:.1f}, mutasyonsuz kontrolde %{control_share * 100:.1f} idi. "
        f"Mutasyonlu grupta fark {direction} ({pct:.1f} yüzde puan)."
    )
    paired = report.get("paired_task_b_share_differences_mutation_minus_controls", {})
    comparison = paired.get("no_reproduction")
    if comparison and comparison.get("ci95_low") is not None:
        finding += (
            f" Mutasyonlu − çoğalmasız kontrol eşlenmiş farkı "
            f"%{comparison['mean'] * 100:.1f} yüzde puan "
            f"(95% GA %{comparison['ci95_low'] * 100:.1f} ile "
            f"%{comparison['ci95_high'] * 100:.1f})."
        )
    criterion = report.get("adaptation_criterion", {})
    if criterion:
        finding += (
            " Önceden belirlenen ölçüte göre iki kontrolün de eşlenmiş %95 güven "
            + ("aralığının alt sınırı sıfırın üstünde; bu simülasyonda ölçüt karşılandı."
               if criterion.get("met") else
               "aralığı sıfırın üstünde değil; uyum gösterildiği sonucuna varılamaz.")
        )
    return {
        "what_was_tested": (
            f"Sanal ortam {shift}. adımda A görevinden B görevine geçirildi. "
            f"Mutasyonlu grup, aynı tohumlardaki{controls_text} karşılaştırıldı."
        ),
        "finding": finding,
        "meaning": "Bu, sadece simülatörde tanımlanan görev ve ödül kuralları altında görülen farktır; simülatör sonucu kodla hesaplanmıştır.",
        "limits": "Bu sonuç gerçek canlıların uyum sağladığını veya yapay zekânın model ağırlıklarını öğrendiğini göstermez; yalnızca sanal genom değişimini ölçer.",
    }

def explain_discovery_sweep(report):
    """Translate a bounded sweep's measured effect and evidence limit."""
    status = report.get("status")
    candidate = report.get("selected_candidate") or {}
    confirmation = report.get("confirmation") or {}
    design = report.get("design", {})
    mutation_rate = candidate.get("mutation_rate")
    screen_n = len(design.get("screening_seeds", []))
    confirm_n = len(design.get("confirmation_seeds", []))

    if status == "replicated_simulation_candidate" and confirmation:
        difference = float(confirmation.get("mean_difference", 0))
        low = confirmation.get("approx_ci95_low")
        high = confirmation.get("approx_ci95_high")
        rate_text = f"{float(mutation_rate) * 100:g}%" if mutation_rate is not None else "seçilen"
        details = (
            f"İlk taramada {screen_n} farklı başlangıç kullanıldı; seçilen ayar "
            f"tarama dışında tutulan {confirm_n} başlangıçla tekrar sınandı."
        )
        if low is not None and high is not None:
            details += (
                f" Yaklaşık belirsizlik aralığı {float(low) * 100:.1f}–"
                f"{float(high) * 100:.1f} yüzde puan."
            )
        finding = (
            f"Bu simülasyonda {rate_text} mutasyon ayarında, son ölçümde "
            f"B göreviyle ilişkili sanal genom payı kontrol grubundan ortalama "
            f"{difference * 100:.1f} yüzde puan yüksekti. {details}"
        )
        limit = (
            "Bu, yalnızca laboratuvarın basitleştirilmiş bilgisayar modelinde görülen bir farktır. "
            "Gerçek hücrelerde veya doğada aynı sonucun olacağını göstermez."
        )
    elif status == "not_reproduced_on_confirmation_seeds":
        finding = (
            "İlk taramada umut veren bir ayar çıktı; ancak ayrı başlangıçlarla yapılan tekrar "
            "aynı farkı desteklemedi. Bu nedenle şu an simülatörde bile tekrarlanmış bir bulgu yok."
        )
        limit = "İlk tarama sonucu tek başına güvenilir bir keşif sayılmaz; daha fazla sınama gerekir."
    else:
        finding = "Bu sınırlı taramada kontrol grubundan daha iyi sonuç veren bir ayar bulunmadı."
        limit = "Bu, hiçbir ayarın işe yaramayacağını kanıtlamaz; yalnızca denenen ayarlarda aday çıkmadı."

    return {
        "finding": finding,
        "limit": limit,
        "warning_explanation": (
            "Ekrandaki uyarı, sonucun ne olmadığını açıklar; yukarıdaki ölçüm ise "
            "simülatörde ne görüldüğünü anlatır."
        ),
    }


def render_explanation(st, explanation, *, key):
    """Render an accessible result card with consistent wording."""
    with st.expander("Sonucu sade dille açıkla", key=key):
        st.markdown(f"**Ne denendi?** {explanation['what_was_tested']}")
        st.markdown(f"**Ne bulundu?** {explanation['finding']}")
        st.markdown(f"**Bu ne anlama geliyor?** {explanation['meaning']}")
        st.markdown(f"**Sınırı ne?** {explanation['limits']}")


