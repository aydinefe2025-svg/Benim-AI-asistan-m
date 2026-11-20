"""Contract for a free, independent and safe CANO health-to-action loop.

Mock only the outside network. Execute CANO's *real* weather routing function
and require source-grounded answer, not a proxy 200 or an AI-generated claim.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import unittest

from core.cano_continuous_verifier import run_checks


APP = Path(__file__).resolve().parents[1] / "app.py"
OFFSET = timezone(timedelta(hours=3))


class Response:
    def __init__(self, status_code=200, data=None, text=""):
        self.status_code = status_code
        self._data = data
        self.text = text

    def json(self):
        return self._data


def live_fixtures():
    now = datetime.now(timezone.utc).astimezone(OFFSET)
    geo = {
        "results": [
            {"name": "Ödemiş", "country_code": "TR", "admin1": "İzmir",
             "admin2": "Ödemiş İlçesi", "latitude": 38.2278,
             "longitude": 27.96955},
            {"name": "Ödemiş", "country_code": "TR", "admin1": "Karabük",
             "admin2": "Karabuk", "latitude": 41.15884,
             "longitude": 32.5935},
            {"name": "Ödemiş", "country_code": "TR", "admin1": "Çankırı",
             "admin2": "Ilgaz İlçesi", "latitude": 40.948,
             "longitude": 33.55396},
            {"name": "Ödemiş", "country_code": "TR", "admin1": "Batman",
             "admin2": "Batman", "latitude": 38.03066,
             "longitude": 41.22681},
            {"name": "Ödemiş", "country_code": "TR", "admin1": "Adıyaman",
             "admin2": "Kâhta İlçesi", "latitude": 37.65812,
             "longitude": 38.76215},
        ]
    }
    forecast = {
        "utc_offset_seconds": 10800,
        "current_units": {
            "temperature_2m": "°C",
            "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
        },
        "current": {
            "time": now.strftime("%Y-%m-%dT%H:%M"),
            "temperature_2m": 17.6,
            "relative_humidity_2m": 76,
            "wind_speed_10m": 9.7,
            "weather_code": 2,
        },
        "daily_units": {
            "temperature_2m_min": "°C",
            "temperature_2m_max": "°C",
        },
        "daily": {
            "time": [(now.date() + timedelta(days=i)).isoformat()
                     for i in range(3)],
            "temperature_2m_min": [12.4, 11.1, 13.2],
            "temperature_2m_max": [20.0, 21.5, 22.8],
        },
    }
    return geo, forecast


class FakeNetwork:
    def __init__(self, *, public_status=200, public_text="streamlit app",
                 health_status=200, health_text="ok",
                 stale=False, error_text=None):
        self.calls = []
        self.public_status = public_status
        self.public_text = public_text
        self.health_status = health_status
        self.health_text = health_text
        self.geo, self.weather = live_fixtures()
        if stale:
            self.weather["current"]["time"] = "2000-01-01T00:00"
        self.error_text = error_text

    def __call__(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error_text is not None:
            raise OSError(self.error_text)
        if url == "https://benim-ai-asistan-streamlit.onrender.com/":
            return Response(self.public_status, text=self.public_text)
        if url == "https://benim-ai-asistan-streamlit.onrender.com/_stcore/health":
            return Response(self.health_status, text=self.health_text)
        if url == "https://geocoding-api.open-meteo.com/v1/search":
            return Response(data=self.geo)
        if url == "https://api.open-meteo.com/v1/forecast":
            params = kwargs["params"]
            # Guard against a regression to the Karabük/Çankırı homonyms.
            if (params["latitude"], params["longitude"]) != (38.2278, 27.96955):
                return Response(400)
            return Response(data=self.weather)
        if url.startswith("https://wttr.in/"):
            raise AssertionError("The network layer must simulate wttr timeout")
        raise AssertionError("Unapproved endpoint: " + url)


class ContinuousVerificationTests(unittest.TestCase):
    def test_live_acceptance_checks_actual_routing_and_provenance(self):
        network = FakeNetwork()
        report = run_checks(network, app_path=APP)
        self.assertEqual("ok", report["verdict"], report)
        self.assertEqual(set(report["checks"]), {
            "public_startup", "current_weather_failover",
            "dated_forecast_failover",
        })
        self.assertTrue(all(check["ok"] for check in report["checks"].values()))
        self.assertEqual([], report["failures"])
        self.assertEqual({
            "authenticated_e2e": False,
            "primary_weather_provider_simulated_unavailable": True,
            "third_party_credentials_sent": False,
        }, report["scope"])
        hosts = [url for url, _ in network.calls]
        self.assertEqual(1, hosts.count(
            "https://benim-ai-asistan-streamlit.onrender.com/"))
        self.assertEqual(1, hosts.count(
            "https://benim-ai-asistan-streamlit.onrender.com/_stcore/health"))
        self.assertEqual(2, hosts.count(
            "https://geocoding-api.open-meteo.com/v1/search"))
        self.assertEqual(2, hosts.count(
            "https://api.open-meteo.com/v1/forecast"))
        self.assertTrue(all(
            "Authorization" not in kwargs.get("headers", {})
            for _, kwargs in network.calls
        ))

    def test_rebranded_streamlit_page_uses_health_endpoint_not_branding(self):
        network = FakeNetwork(public_text="<html>custom CANO page</html>")
        report = run_checks(network, app_path=APP)
        self.assertEqual("ok", report["verdict"], report)
        self.assertTrue(report["checks"]["public_startup"]["ok"])
        self.assertIn(
            "https://benim-ai-asistan-streamlit.onrender.com/_stcore/health",
            [url for url, _ in network.calls],
        )

    def test_an_unrelated_public_page_without_streamlit_health_is_not_accepted(self):
        report = run_checks(
            FakeNetwork(public_text="unrelated web page", health_text="not ok"),
                            app_path=APP)
        self.assertEqual("failed", report["verdict"])
        self.assertFalse(report["checks"]["public_startup"]["ok"])
        self.assertEqual(
            "health_body_not_ok", report["checks"]["public_startup"]["reason"])
        self.assertTrue(report["checks"]["current_weather_failover"]["ok"])
        self.assertIn("public_startup", report["failures"])

    def test_non_200_root_is_not_accepted_even_if_health_route_is_healthy(self):
        network = FakeNetwork(public_status=503)
        report = run_checks(network, app_path=APP)
        self.assertFalse(report["checks"]["public_startup"]["ok"])
        self.assertEqual("root_http_503", report["checks"]["public_startup"]["reason"])
        self.assertNotIn(
            "https://benim-ai-asistan-streamlit.onrender.com/_stcore/health",
            [url for url, _ in network.calls],
        )

    def test_health_http_status_is_reported_without_response_body(self):
        private = "private response body must never be logged"
        report = run_checks(
            FakeNetwork(health_status=404, health_text=private), app_path=APP)
        encoded = json.dumps(report)
        self.assertEqual("health_http_404", report["checks"]["public_startup"]["reason"])
        self.assertNotIn(private, encoded)

    def test_stale_or_invalid_weather_is_an_actionable_failure(self):
        report = run_checks(FakeNetwork(stale=True), app_path=APP)
        self.assertEqual("failed", report["verdict"])
        self.assertFalse(report["checks"]["current_weather_failover"]["ok"])
        self.assertFalse(report["checks"]["dated_forecast_failover"]["ok"])
        self.assertIn("dated_forecast_failover", report["failures"])

    def test_request_exception_is_redacted_and_no_false_pass(self):
        private = "postgresql://do-not-log-username:password@secret-host/db"
        report = run_checks(FakeNetwork(error_text=private), app_path=APP)
        encoded = json.dumps(report)
        self.assertEqual("failed", report["verdict"])
        self.assertNotIn(private, encoded)
        self.assertNotIn("secret-host", encoded)
        self.assertEqual(3, len(report["failures"]))

    def test_report_does_not_mark_auth_or_git_operations_completed(self):
        report = run_checks(FakeNetwork(), app_path=APP)
        self.assertNotIn("deployed", report)
        self.assertNotIn("PR created", json.dumps(report))
        self.assertFalse(report["scope"]["authenticated_e2e"])

    def test_scheduled_workflow_has_dedup_alert_without_secrets_or_automerge(self):
        workflow = (APP.parent / ".github/workflows/cano-independent-verifier.yml")
        self.assertTrue(workflow.is_file())
        content = workflow.read_text(encoding="utf-8")
        self.assertIn("schedule:", content)
        self.assertIn("workflow_dispatch:", content)
        self.assertIn("issues: write", content)
        self.assertIn("gh issue list", content)
        self.assertIn("gh issue create", content)
        self.assertIn("python -m scripts.cano_independent_verifier", content)
        self.assertNotIn("pull_request_target:", content)
        self.assertNotIn("gh pr merge", content)
        self.assertNotIn("Render deploy", content)
        self.assertNotIn("secrets.", content)
        # Reviewed new workflows use immutable commit refs.
        import re
        refs = re.findall(r"uses:\s+([^\s]+)", content)
        self.assertTrue(refs)
        self.assertTrue(all(
            re.fullmatch(r"actions/[\w-]+@[a-f0-9]{40}", x)
            for x in refs
        ))


if __name__ == "__main__":
    unittest.main()


