"""Read-only, public GitHub Actions results for the Render colony panel.

Only small, non-sensitive simulation reports are read from a public repository.
No GitHub token, database credential, or user data is used by this bridge.
"""
from __future__ import annotations

import json
import math
import threading
import time


REPOSITORY = "aydinefe2025-svg/Benim-AI-asistan-m"
RAW_REPORT_URL = (
    f"https://raw.githubusercontent.com/{REPOSITORY}/cano-latest/colony-cycle.json"
)
MAX_REPORT_BYTES = 1_000_000
EXPECTED_AGENTS = {"evidence", "generation", "continuity", "security"}


class ColonyStatusUnavailable(RuntimeError):
    """Safe, user-facing category; raw response bodies are never surfaced."""

_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE_VALUE = None
_STATUS_CACHE_UNTIL = 0.0
_STATUS_CACHE_ERROR = None


def _load_process_cached(loader, *, force_refresh=False):
    """Share the public result across Streamlit sessions on this one process."""
    global _STATUS_CACHE_VALUE, _STATUS_CACHE_UNTIL, _STATUS_CACHE_ERROR
    now = time.monotonic()
    with _STATUS_CACHE_LOCK:
        if not force_refresh and now < _STATUS_CACHE_UNTIL:
            if _STATUS_CACHE_ERROR is not None:
                raise ColonyStatusUnavailable(_STATUS_CACHE_ERROR)
            return _STATUS_CACHE_VALUE
        try:
            value = loader()
        except ColonyStatusUnavailable as exc:
            _STATUS_CACHE_VALUE = None
            _STATUS_CACHE_ERROR = str(exc)
            _STATUS_CACHE_UNTIL = now + 30
            raise
        _STATUS_CACHE_VALUE = value
        _STATUS_CACHE_ERROR = None
        _STATUS_CACHE_UNTIL = now + 300
        return value


def _get_report(request_get) -> dict:
    response = request_get(
        RAW_REPORT_URL,
        headers={"Accept": "application/json",
                 "User-Agent": "organism-lab-readonly-colony-panel"},
        timeout=8,
        stream=True,
    )
    response.raise_for_status()
    declared = response.headers.get("Content-Length")
    if declared and int(declared) > MAX_REPORT_BYTES:
        raise ColonyStatusUnavailable("cycle_report_too_large")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=32_000):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > MAX_REPORT_BYTES:
            raise ColonyStatusUnavailable("cycle_report_too_large")
    report = json.loads(bytes(body).decode("utf-8"))
    if not isinstance(report, dict):
        raise ColonyStatusUnavailable("invalid_cycle_report")
    raw_run_id = report.get("github_run_id")
    if not isinstance(raw_run_id, (str, int)) or not str(raw_run_id).isdigit():
        raise ColonyStatusUnavailable("invalid_workflow_run")
    return report, int(raw_run_id)


def _validate_report(report: object, run_id: int) -> dict:
    if not isinstance(report, dict):
        raise ColonyStatusUnavailable("invalid_cycle_report")
    cycle = report.get("cycle")
    generation = report.get("virtual_generation")
    specialists = report.get("specialist_agents")
    if (str(report.get("github_run_id")) != str(run_id)
            or report.get("db_integrity") != "ok"
            or not isinstance(report.get("continuity"), dict)
            or report["continuity"].get("increment_verified") is not True
            or report.get("mode") != "bounded_virtual_reproduction_with_held_out_validation"
            or not isinstance(cycle, dict)
            or type(cycle.get("tick_id")) is not int
            or not isinstance(generation, dict)
            or generation.get("generation_id") != cycle["tick_id"]
            or generation.get("offspring_scope") != "bounded toy digital VM only"
            or generation.get("model_weights_updated") is not False):
        raise ColonyStatusUnavailable("cycle_integrity_check_failed")
    if not isinstance(specialists, dict) or specialists.get("status") != "passed":
        raise ColonyStatusUnavailable("specialist_agents_not_passed")
    roles = specialists.get("roles")
    if (not isinstance(roles, list)
            or not all(isinstance(item, dict) for item in roles)
            or specialists.get("launched") != len(EXPECTED_AGENTS)
            or {item.get("role") for item in roles if isinstance(item, dict)} != EXPECTED_AGENTS
            or any(item.get("status") != "passed"
                   or item.get("execution") != "isolated_read_only_subprocess"
                   or item.get("model_calls") != 0
                   for item in roles if isinstance(item, dict))):
        raise ColonyStatusUnavailable("specialist_agent_results_invalid")
    if generation.get("lesson_status") not in {"transferred", "rejected"}:
        raise ColonyStatusUnavailable("generation_decision_invalid")
    measured = (
        generation.get("candidate_mutation_rate"),
        generation.get("next_generation_mutation_rate"),
        generation.get("training", {}).get("ci95_low"),
        generation.get("held_out_confirmation", {}).get("ci95_low"),
        generation.get("training", {}).get("candidate_mean_births"),
        generation.get("training", {}).get("candidate_mean_final_population"),
    )
    if any(type(item) not in (int, float) or not math.isfinite(item) for item in measured):
        raise ColonyStatusUnavailable("generation_metrics_invalid")
    # Only fixed, measured fields are returned to the UI.
    return {
        "tick_id": cycle["tick_id"],
        "generation_id": generation["generation_id"],
        "lesson_status": generation.get("lesson_status"),
        "candidate_mutation_rate": generation.get("candidate_mutation_rate"),
        "next_generation_mutation_rate": generation.get("next_generation_mutation_rate"),
        "training_ci95_low": generation.get("training", {}).get("ci95_low"),
        "confirmation_ci95_low": generation.get("held_out_confirmation", {}).get("ci95_low"),
        "births": generation.get("training", {}).get("candidate_mean_births"),
        "population": generation.get("training", {}).get("candidate_mean_final_population"),
        "specialist_agents": roles,
        "timestamp": report.get("timestamp"),
    }


def load_latest_colony_status(request_get=None) -> dict:
    """Read the latest validated public report without GitHub REST API calls."""
    if request_get is None:
        import requests
        request_get = requests.get
    try:
        report, run_id = _get_report(request_get)
        summary = _validate_report(report, run_id)
        return {
            "state": "success",
            "run_id": run_id,
            "run_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
            "latest_run_state": "completed",
            "latest_run_conclusion": "success",
            "generated_at": summary.pop("timestamp"),
            "report": summary,
        }
    except ColonyStatusUnavailable:
        raise
    except Exception as exc:
        # Surface only fixed diagnostic codes; never expose response data or URLs.
        code = "github_cycle_unavailable"
        try:
            import requests
            if isinstance(exc, requests.Timeout):
                code = "github_timeout"
            elif isinstance(exc, requests.HTTPError):
                status = getattr(getattr(exc, "response", None), "status_code", None)
                code = {
                    401: "github_http_401",
                    403: "github_http_403_or_rate_limit",
                    404: "github_http_404",
                    429: "github_http_429",
                }.get(status, "github_http_5xx" if isinstance(status, int) and status >= 500 else "github_http_error")
            elif isinstance(exc, json.JSONDecodeError):
                code = "artifact_json_invalid"
        except Exception:
            pass
        raise ColonyStatusUnavailable(code) from None


def _lesson_explanation(report: dict) -> tuple[str, str]:
    """Translate the measured transfer decision into plain Turkish."""
    training_low = report["training_ci95_low"]
    confirmation_low = report["confirmation_ci95_low"]
    candidate_rate = report["candidate_mutation_rate"]
    next_rate = report["next_generation_mutation_rate"]
    if report["lesson_status"] == "transferred":
        return (
            "Sanal deneye aktarıldı",
            f"Aday ayar ({candidate_rate:.3f}) eğitimde ve ayrı doğrulama grubunda "
            f"olumlu kanıt eşiğini geçti; sonraki sanal nesilde {next_rate:.3f} ayarı "
            "kullanılacak. Bu sonuç yalnızca basitleştirilmiş dijital simülasyona aittir; "
            "yapay zekâ modelinin ağırlıkları değişmez."
        )
    return (
        "Aktarılmadı",
        f"Aday ayar ({candidate_rate:.3f}) yeterli iyileşme kanıtı göstermedi. "
        f"Eğitim testinin %95 aralık alt sınırı {training_low:.3f}, ayrı doğrulamanın "
        f"alt sınırı {confirmation_low:.3f}; aktarım için ikisinin de sıfırın üstünde "
        f"olması gerekir. Bu nedenle sonraki sanal turda {next_rate:.3f} ayarı korundu. "
        "Sonuç yalnızca toy dijital VM içindir."
    )


def render_colony_status_panel(st, *, loader=load_latest_colony_status) -> None:
    """Render an authenticated app's bounded hourly Actions result summary."""
    cache_key = "_cano_github_cycle_status"
    now = __import__("time").time()
    cached = st.session_state.get(cache_key)
    force_refresh = st.button("Actions sonuçlarını yenile", key="refresh_github_colony_status")
    if force_refresh:
        st.session_state.pop(cache_key, None)
        cached = None
    with st.expander("⏱ Otomatik döngü ve bağımsız yazılım ajanları", expanded=True):
        st.caption(
            "Bu panel, GitHub Actions'taki son doğrulanmış dijital çevrimi gösterir. "
            "Dört ajan ayrı salt-okunur süreçlerde çalışır; LLM çağırmaz, kod veya "
            "üretim verisi değiştirmez."
        )
        if not isinstance(cached, dict) or now - cached.get("fetched_at", 0) >= 300:
            try:
                cached = {"fetched_at": now, "value": _load_process_cached(loader, force_refresh=force_refresh)}
                st.session_state[cache_key] = cached
            except ColonyStatusUnavailable as exc:
                st.warning(f"GitHub Actions raporu okunamadı (tanı kodu: {exc}). Daha sonra yenile.")
                return
        value = cached["value"]
        if value.get("state") == "no_runs":
            st.info("Henüz tamamlanmış CANO Actions çevrimi bulunmuyor.")
            return
        if value.get("state") != "success":
            st.info(f"Son otomatik çevrim durumu: {value.get('state', 'bilinmiyor')}.")
            return
        report = value["report"]
        if value.get("latest_run_state") != "completed" or value.get("latest_run_conclusion") != "success":
            st.warning("En son Actions çalışması henüz başarıyla tamamlanmadı; aşağıda son başarılı rapor gösteriliyor.")
        a, b, c = st.columns(3)
        a.metric("Dijital çevrim", report["tick_id"])
        b.metric("Sanal nesil", report["generation_id"])
        lesson_label, lesson_detail = _lesson_explanation(report)
        c.metric("Ders aktarımı", lesson_label)
        st.info(lesson_detail)
        st.caption(
            f"Aday mutasyon {report['candidate_mutation_rate']:.3f} · "
            f"sonraki nesil {report['next_generation_mutation_rate']:.3f} · "
            f"eğitim alt sınırı {report['training_ci95_low']:.3f} · "
            f"ayrılmış doğrulama alt sınırı {report['confirmation_ci95_low']:.3f}"
        )
        if isinstance(report.get("births"), (int, float)):
            st.caption(f"Deneme ortalaması: {report['births']:.1f} sanal doğum; "
                       f"son nüfus {report['population']:.1f}. Bunlar yalnızca toy VM ölçümleridir.")
        st.markdown(f"[Actions çalışmasını aç]({value['run_url']})")
        agents = report["specialist_agents"]
        st.write("Bağımsız doğrulama ajanları")
        st.dataframe(
            [{"Ajan": agent["label"], "Durum": "Geçti",
              "Denetimler": ", ".join(agent["checks"])} for agent in agents],
            width="stretch", hide_index=True,
        )
        st.caption("Bu ajanlar ayrı Python süreçleridir; sohbet modeli veya otonom kod geliştirici değildir.")
