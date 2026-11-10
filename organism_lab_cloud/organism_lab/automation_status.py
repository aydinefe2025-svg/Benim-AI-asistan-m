"""Read-only, public GitHub Actions results for the Render colony panel.

Only small, non-sensitive simulation reports are read from a public repository.
No GitHub token, database credential, or user data is used by this bridge.
"""
from __future__ import annotations

from io import BytesIO
import hashlib
import json
import math
import re
import zipfile
import threading
import time

REPOSITORY = "aydinefe2025-svg/Benim-AI-asistan-m"
WORKFLOW_FILE = "cano-colony-cycle.yml"
PUBLISHED_STATUS_URL = (
    "https://raw.githubusercontent.com/aydinefe2025-svg/Benim-AI-asistan-m/"
    "cano-latest/colony-cycle.json"
)
MAX_ARCHIVE_BYTES = 8_000_000
MAX_REPORT_BYTES = 1_000_000
EXPECTED_AGENTS = {"evidence", "generation", "continuity", "security"}
RUNS_URL = (
    f"https://api.github.com/repos/{REPOSITORY}/actions/workflows/"
    f"{WORKFLOW_FILE}/runs?branch=main&per_page=5"
)


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
        "continued_from_tick": report["continuity"].get("previous_tick_id"),
        "specialist_agents": roles,
        "timestamp": report.get("timestamp"),
    }


def load_latest_colony_status(request_get=None) -> dict:
    """Fetch the public status feed, falling back to the Actions API."""
    if request_get is None:
        import requests
        request_get = requests.get
    try:
        # The existing public cano-latest branch feed avoids GitHub REST's low
        # unauthenticated rate limit on Render. It contains only the latest
        # successful, validated toy report.
        try:
            published = _get_json(request_get, PUBLISHED_STATUS_URL)
        except Exception:
            published = {}
        if "github_run_id" in published:
            try:
                run_id = int(published["github_run_id"])
            except (TypeError, ValueError):
                raise ColonyStatusUnavailable("invalid_published_run_id") from None
            summary = _validate_report(published, run_id)
            return {
                "state": "success",
                "run_id": run_id,
                "run_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
                "latest_run_state": "completed",
                "latest_run_conclusion": "success",
                "generated_at": summary.pop("timestamp"),
                "report": summary,
            }
        payload = _get_json(request_get, RUNS_URL)
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            raise ColonyStatusUnavailable("invalid_workflow_run_list")
        if not runs:
            return {"state": "no_runs"}
        latest = runs[0]
        latest_id = latest.get("id")
        if type(latest_id) is not int:
            raise ColonyStatusUnavailable("invalid_workflow_run")
        previous_success = next((
            run for run in runs
            if run.get("status") == "completed" and run.get("conclusion") == "success"
            and type(run.get("id")) is int
        ), None)
        if previous_success is None:
            return {
                "state": latest.get("status", "unknown"),
                "conclusion": latest.get("conclusion"),
                "run_id": latest_id,
            }
        run_id = previous_success["id"]
        artifacts_url = (
            f"https://api.github.com/repos/{REPOSITORY}/actions/runs/{run_id}/artifacts"
        )
        artifacts = _get_json(request_get, artifacts_url).get("artifacts")
        if not isinstance(artifacts, list):
            raise ColonyStatusUnavailable("invalid_artifact_list")
        expected_name = f"cano-colony-cycle-{run_id}"
        artifact = next((item for item in artifacts
                         if isinstance(item, dict) and item.get("name") == expected_name
                         and item.get("expired") is False and type(item.get("id")) is int), None)
        if artifact is None or artifact.get("size_in_bytes", MAX_ARCHIVE_BYTES + 1) > MAX_ARCHIVE_BYTES:
            raise ColonyStatusUnavailable("cycle_artifact_missing")
        archive_url = (
            f"https://api.github.com/repos/{REPOSITORY}/actions/artifacts/"
            f"{artifact['id']}/zip"
        )
        archive = _bounded_download(request_get, archive_url)
        digest = artifact.get("digest")
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
            raise ColonyStatusUnavailable("artifact_digest_missing")
        if hashlib.sha256(archive).hexdigest() != digest.removeprefix("sha256:"):
            raise ColonyStatusUnavailable("artifact_digest_mismatch")
        with zipfile.ZipFile(BytesIO(archive)) as bundle:
            info = next((item for item in bundle.infolist()
                         if item.filename == "colony-cycle.json"), None)
            if info is None or info.file_size > MAX_REPORT_BYTES:
                raise ColonyStatusUnavailable("cycle_report_missing_or_too_large")
            raw = bundle.read(info)
        report = json.loads(raw.decode("utf-8"))
        summary = _validate_report(report, run_id)
        return {
            "state": "success",
            "run_id": run_id,
            "run_url": f"https://github.com/{REPOSITORY}/actions/runs/{run_id}",
            "latest_run_state": latest.get("status"),
            "latest_run_conclusion": latest.get("conclusion"),
            "generated_at": summary.pop("timestamp"),
            "report": summary,
        }
    except ColonyStatusUnavailable:
        raise
    except Exception as exc:
        # Expose only a fixed diagnostic code; never show URLs, response bodies,
        # headers, credentials, or arbitrary exception text in the app.
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
            elif isinstance(exc, zipfile.BadZipFile):
                code = "artifact_not_a_valid_zip"
            elif isinstance(exc, json.JSONDecodeError):
                code = "artifact_json_invalid"
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
        report = value.get("report")
        required_report_fields = {
            "tick_id", "generation_id", "lesson_status", "candidate_mutation_rate",
            "next_generation_mutation_rate", "training_ci95_low",
            "confirmation_ci95_low", "specialist_agents",
        }
        if (not isinstance(report, dict)
                or not required_report_fields.issubset(report)
                or not isinstance(value.get("run_url"), str)):
            st.warning("GitHub Actions raporu eksik veya beklenmeyen biçimde; güvenli biçimde gösterilmedi.")
            return
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
        if report["continued_from_tick"] is None:
            st.caption("Bu, mevcut kayıt dizisindeki ilk çevrim; önceki nesilden devam kaydı yok.")
        else:
            st.caption(f"Önceki kayıtlı çevrim #{report['continued_from_tick']} üzerinden devam etti.")
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

