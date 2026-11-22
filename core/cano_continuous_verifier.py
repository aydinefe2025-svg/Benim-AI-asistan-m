"""CANO's independent, credential-free continuous acceptance controller.

This is a read-only verification worker, NOT a self-editing code agent.
It exercises the real app weather router against live free Open-Meteo, while
simulating the primary wttr.in outage that caused the user-visible defect.
A scheduled GitHub Action owns the failure-to-deduplicated-issue handoff.

Never log HTTP bodies, exception messages, owner identifiers or credentials.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlencode, urlsplit

from core.weather_reliability import parse_wttr_current, weather_direct_reply


_APP = Path(__file__).resolve().parents[1] / "app.py"
_PUBLIC = "https://benim-ai-asistan-streamlit.onrender.com/"
_PRIMARY = "wttr.in"
_ALLOWED_BACKUPS = frozenset({
    "geocoding-api.open-meteo.com",
    "api.open-meteo.com",
})
_QUESTION_CURRENT = "İzmir Ödemiş hava durumu"
_QUESTION_FORECAST = "İzmir Ödemiş hava tahminleri"


class _NotAvailable:
    status_code = 503


class _WeatherBoundary:
    """Keep any test egress fixed-host; simulate wttr.in being unavailable."""

    def __init__(self, real_get):
        self._real_get = real_get
        self.locations = []

    def get(self, url, **kwargs):
        address = urlsplit(url)
        if address.scheme != "https" or address.username or address.password:
            raise ValueError("Unapproved weather endpoint")
        if address.hostname == _PRIMARY:
            return _NotAvailable()
        if address.hostname not in _ALLOWED_BACKUPS:
            raise ValueError("Unapproved weather endpoint")
        if any(k not in {"params", "timeout"} for k in kwargs):
            raise ValueError("Unexpected outbound request options")
        if address.hostname == "api.open-meteo.com":
            params = kwargs.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("Invalid source parameters")
            lat, lon = params.get("latitude"), params.get("longitude")
            self.locations.append((lat, lon))
            # A reply about İzmir must not use a same-name town in Karabük,
            # Çankırı, Batman or Adıyaman, even if those forecasts are valid.
            if (not isinstance(lat, (int, float))
                    or not isinstance(lon, (int, float))
                    or not (37.5 <= lat <= 39.0 and 27.0 <= lon <= 29.0)):
                raise ValueError("Weather location is not İzmir Ödemiş")
        return self._real_get(url, **kwargs)


def _app_search(boundary, path: Path):
    """Compile only the trusted repository search function, not Streamlit UI."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    func = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef)
         and n.name == "internette_ara"),
        None,
    )
    if func is None:
        raise ValueError("CANO search route is missing")
    safe_namespace = {
        "requests": SimpleNamespace(get=boundary.get),
        "parse_wttr_current": parse_wttr_current,
        "urlencode": urlencode,
        "re": re,
    }
    exec(compile(ast.Module(body=[func], type_ignores=[]),
                 str(path), "exec"), safe_namespace)
    return safe_namespace["internette_ara"]


def _probe_public(get):
    # Free-tier hosting can require a cold start after inactivity. Retry
    # exactly once only on a recognizable timeout; a 4xx/5xx or connection
    # error must remain a failure, never become a false health PASS.
    try:
        response = get(_PUBLIC, timeout=20)
    except Exception as exc:
        if (not isinstance(exc, TimeoutError)
                and type(exc).__name__ not in {
                    "Timeout", "ConnectTimeout", "ReadTimeout",
                    "ReadTimeoutError",
                }):
            raise
        response = get(_PUBLIC, timeout=60)
    status = getattr(response, "status_code", None)
    if status != 200:
        return False, f"root_http_{status}" if isinstance(status, int) else "root_http_unknown"
    # Streamlit's rendered page is white-labelled by st.set_page_config, so
    # its HTML need not contain the literal word "Streamlit". Confirm the
    # application server with Streamlit's public health endpoint instead.
    health = get(_PUBLIC.rstrip("/") + "/_stcore/health", timeout=10)
    health_status = getattr(health, "status_code", None)
    body = getattr(health, "text", "")
    if health_status != 200:
        reason = (f"health_http_{health_status}" if isinstance(health_status, int)
                  else "health_http_unknown")
        return False, reason
    if not isinstance(body, str) or body.strip().casefold() != "ok":
        return False, "health_body_not_ok"
    return True, None


def _probe_weather(search, *, forecast: bool):
    question = _QUESTION_FORECAST if forecast else _QUESTION_CURRENT
    source = search(question)
    if not isinstance(source, str) or not source.startswith("OPEN_METEO_JSON:"):
        return False
    answer = weather_direct_reply(question, source)
    if (not isinstance(answer, str) or "Ödemiş" not in answer
            or "Open-Meteo" not in answer or "°C" not in answer
            or "Crossref" in answer
            or "doğrulanamadı" in answer.casefold()):
        return False
    if forecast:
        return "3 günlük tahmin" in answer and answer.count("en düşük") == 3
    return "güncel model hava" in answer


def run_checks(get, *, app_path=None):
    """Run bounded acceptance; return only allowlisted outcome codes.

    The report can be uploaded to CI or posted as an incident without risk
    of exposing raw HTTP bodies or exception messages. Production login or
    persistent owner data are deliberately outside this controller's scope.
    """
    checks = {}
    failures = []
    boundary = _WeatherBoundary(get)
    search = None
    path = Path(app_path) if app_path is not None else _APP

    for name in ("public_startup", "current_weather_failover",
                 "dated_forecast_failover"):
        try:
            if name == "public_startup":
                ok, reason = _probe_public(get)
            else:
                if search is None:
                    search = _app_search(boundary, path)
                ok = _probe_weather(
                    search, forecast=(name == "dated_forecast_failover"),
                )
        except Exception:
            # Never serialize upstream exception messages or response bodies.
            ok = False
            reason = "request_failed" if name == "public_startup" else None
        checks[name] = {"ok": bool(ok)}
        if name == "public_startup" and reason:
            checks[name]["reason"] = reason
        if not ok:
            failures.append(name)

    return {
        "verdict": "failed" if failures else "ok",
        "checks": checks,
        "failures": failures,
        "scope": {
            "authenticated_e2e": False,
            "primary_weather_provider_simulated_unavailable": True,
            "third_party_credentials_sent": False,
        },
    }


