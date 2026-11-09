"""Build a small, schema-limited context from the current user's lab results."""
from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def _number(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value):
        return None
    return f"{value:.4g}"


def _metric_line(label: str, value: Any) -> str | None:
    rendered = _number(value)
    return f"- {label}: {rendered}" if rendered is not None else None


def _percent_line(label: str, value: Any) -> str | None:
    rendered = _number(value)
    if rendered is None:
        return None
    return f"{label}: {_number(value * 100)}%"


def summarize_lab_results(state: Mapping[str, Any]) -> str:
    """Return only allow-listed numerical summaries, never arbitrary report text."""
    sections: list[str] = []

    simulation = state.get("organism_result")
    if isinstance(simulation, Mapping):
        metrics = [
            _metric_line("Sanal robot", simulation.get("robots")),
            _metric_line("Sanal organizma", simulation.get("organisms")),
            _metric_line("Başarılı sanal rota", simulation.get("successful_routes")),
        ]
        metrics = [item for item in metrics if item]
        history = simulation.get("history")
        if isinstance(history, list) and history and isinstance(history[-1], Mapping):
            last = history[-1]
            metrics.extend(item for item in (
                _metric_line("Son adım enerji", last.get("energy_left")),
                _metric_line("Son adım malzeme", last.get("materials_left")),
                _metric_line("Son simülasyon adımı", last.get("tick")),
            ) if item)
        if metrics:
            sections.append("Son temel simülasyon:\n" + "\n".join(metrics))

    campaign = state.get("genome_campaign_v2")
    if isinstance(campaign, Mapping) and isinstance(campaign.get("results"), list):
        rows: list[str] = []
        for result in campaign["results"][:5]:
            if not isinstance(result, Mapping):
                continue
            resource = _number(result.get("resource_per_tick"))
            paired = _number(result.get("paired_seeds"))
            difference = result.get("paired_population_difference")
            mean = _number(difference.get("mean")) if isinstance(difference, Mapping) else None
            low = _number(difference.get("ci95_low")) if isinstance(difference, Mapping) else None
            high = _number(difference.get("ci95_high")) if isinstance(difference, Mapping) else None
            if resource is not None and paired is not None and mean is not None:
                interval = (f"; yaklaşık %95 aralık {low}–{high}"
                            if low is not None and high is not None else "")
                rows.append(
                    f"- Kaynak/adım {resource}, eşlenmiş tohum {paired}: "
                    f"çoğalma-kapalı kontrole göre ortalama son nüfus farkı {mean}{interval}"
                )
        if rows:
            sections.append("Genom çoğaltma kampanyası (yalnızca toy simülatör):\n" + "\n".join(rows))

    adaptation = state.get("environment_shift_report")
    if isinstance(adaptation, Mapping) and isinstance(adaptation.get("results"), list):
        rows = []
        labels = {"mutation": "Mutasyonlu soy", "no_mutation": "Mutasyonsuz kontrol"}
        for result in adaptation["results"][:2]:
            if not isinstance(result, Mapping) or result.get("arm") not in labels:
                continue
            values = [
                _metric_line("son nüfus ortalaması", result.get("final_population_mean")),
                _percent_line("TASK_B taşıyan pay", result.get("final_task_b_share_mean")),
                _percent_line("uyum sağlayan tohum oranı", result.get("adapted_seed_rate")),
                _metric_line("ortalama uyum gecikmesi (adım)", result.get("adaptation_lag_mean_ticks")),
            ]
            rows.append(labels[result["arm"]] + ": " + "; ".join(item for item in values if item))
        if rows:
            sections.append("TASK_A→TASK_B uyum deneyi (yalnızca toy simülatör):\n" + "\n".join("- " + row for row in rows))

    if not sections:
        return ""
    return (
        "OTURUMDAKİ SON LABORATUVAR ÖZETİ (yalnızca sayısal simülasyon verisi; "
        "gerçek biyolojik kanıt değildir):\n" + "\n\n".join(sections)
    )[:5000]

