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
WORKFLOW_FILE = "cano-colony-cycle.yml"
MAX_ARCHIVE_BYTES = 8_000_000
MAX_REPORT_BYTES = 1_000_000
EXPECTED_AGENTS = {"evidence", "generation", "continuity", "security"}
REPORT_URL = f"https://raw.githubusercontent.com/{REPOSITORY}/cano-latest/colony-cycle.json"


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


def _get_json(request_get, url: str) -> dict:
    response = request_get(
        url,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "organism-lab-readonly-colony-panel"},
        timeout=8,
    )
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ColonyStatusUnavailable("invalid_github_response")
    return value


def _bounded_download(request_get, url: str) -> bytes:
    response = request_get(
        url,
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "organism-lab-readonly-colony-panel"},
        timeout=12,
        stream=True,
    )
    response.raise_for_status()
    declared = response.headers.get("Content-Length")
    if declared and int(declared) > MAX_ARCHIVE_BYTES:
        raise ColonyStatusUnavailable("artifact_too_large")
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64_000):
        if not chunk:
            continue
        body.extend(chunk)
        if len(body) > MAX_ARCHIVE_BYTES:
            raise ColonyStatusUnavailable("artifact_too_large")
    return bytes(body)


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
    """Read the latest validated public summary without the GitHub REST API."""
    if request_get is None:
        import requests
        request_get = requests.get
    url = f"{REPORT_URL}?v={int(time.time())}"
    try:
        response = request_get(
            url,
            headers={"Accept": "application/json",
                     "User-Agent": "organism-lab-readonly-colony-panel"},
            timeout=8,
        )
        response.raise_for_status()
        raw = getattr(response, "content", None)
        if raw is not None and len(raw) > MAX_REPORT_BYTES:
            raise ColonyStatusUnavailable("cycle_report_too_large")
        report = response.json()
        run_value = report.get("github_run_id") if isinstance(report, dict) else None
        if not isinstance(run_value, (int, str)) or not str(run_value).isdigit():
            raise ColonyStatusUnavailable("invalid_cycle_run_id")
        run_id = int(run_value)
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
        code = "colony_report_unavailable"
        try:
            import requests
            if isinstance(exc, requests.Timeout):
                code = "report_timeout"
            elif isinstance(exc, requests.HTTPError):
                status = getattr(getattr(exc, "response", None), "status_code", None)
                code = {
                    404: "report_not_published",
                    429: "report_rate_limited",
                }.get(status, "report_http_5xx" if isinstance(status, int) and status >= 500 else "report_http_error")
            elif isinstance(exc, json.JSONDecodeError):
                code = "report_json_invalid"
        except Exception:
            pass
        raise ColonyStatusUnavailable(code) from None



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
        c.metric("Ders aktarımı", report["lesson_status"])
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
