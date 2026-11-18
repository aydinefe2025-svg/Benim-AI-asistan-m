"""TDD: production weather must recover from an unavailable wttr.in provider.

These fixture tests never contact external APIs and never invent weather. They
exercise the real Streamlit search helper plus separately revalidated replies.
"""
from datetime import datetime, timedelta, timezone
import json
import types
import unittest

from tests.test_search_provider_urls import load_search_function


def fake_response(*, status=200, payload=None, text=""):
    return types.SimpleNamespace(
        status_code=status, json=lambda: payload, text=text,
    )


def valid_meteo_payload(*, old=False, forecast=False):
    now = datetime.now(timezone.utc) + timedelta(hours=3)
    if old:
        now -= timedelta(days=2)
    days = [(now.date() + timedelta(days=i)).isoformat() for i in range(3)]
    data = {
        "utc_offset_seconds": 10800,
        "current_units": {
            "temperature_2m": "°C", "relative_humidity_2m": "%",
            "wind_speed_10m": "km/h",
        },
        "current": {
            "time": now.strftime("%Y-%m-%dT%H:00"),
            "temperature_2m": 18.4,
            "relative_humidity_2m": 62,
            "wind_speed_10m": 7.2,
            "weather_code": 3,
        },
    }
    if forecast:
        data["daily"] = {
            "time": days,
            "temperature_2m_min": [11.3, 12.1, 13.4],
            "temperature_2m_max": [20.2, 21.8, 22.3],
        }
        data["daily_units"] = {
            "temperature_2m_min": "°C",
            "temperature_2m_max": "°C",
        }
    return data


GEOCODED_ODEMIS = {
    "results": [
        {"name": "Ödemiş", "country_code": "TR",
         "latitude": 38.23, "longitude": 27.97,
         "admin1": "İzmir"},
    ]
}


class OpenMeteoFailoverTests(unittest.TestCase):
    def test_odemis_fallback_when_wttr_returns_non_200(self):
        from core.open_meteo_weather import render_open_meteo_reply
        search, requests = load_search_function()
        requests.get.side_effect = [
            fake_response(status=503),
            fake_response(payload=GEOCODED_ODEMIS),
            fake_response(payload=valid_meteo_payload()),
        ]
        context = search("İzmir Ödemiş hava durumu")
        self.assertTrue(context.startswith("OPEN_METEO_JSON:"), context)
        answer = render_open_meteo_reply("İzmir Ödemiş hava durumu", context)
        self.assertIn("Ödemiş", answer)
        self.assertIn("18.4", answer)
        self.assertIn("Open-Meteo", answer)
        self.assertNotIn("Crossref", answer)
        self.assertNotIn("tahmin uydurmadım", answer)
        calls = requests.get.call_args_list
        self.assertEqual(3, len(calls))
        self.assertTrue(calls[0].args[0].startswith("https://wttr.in/"))
        self.assertEqual("https://geocoding-api.open-meteo.com/v1/search", calls[1].args[0])
        self.assertEqual("Ödemiş", calls[1].kwargs["params"]["name"])
        self.assertEqual("https://api.open-meteo.com/v1/forecast", calls[2].args[0])
        self.assertEqual(38.23, calls[2].kwargs["params"]["latitude"])

    def test_request_exception_from_wttr_reaches_backup_instead_of_generic_failure(self):
        from core.open_meteo_weather import render_open_meteo_reply
        search, requests = load_search_function()
        requests.get.side_effect = [
            OSError("upstream unreachable"),
            fake_response(payload=GEOCODED_ODEMIS),
            fake_response(payload=valid_meteo_payload()),
        ]
        context = search("Ödemiş hava durumu")
        self.assertIn("Open-Meteo", render_open_meteo_reply(
            "Ödemiş hava durumu", context))
        self.assertEqual(3, requests.get.call_count)

    def test_forecast_has_three_dates_and_validated_minimum_maximum(self):
        from core.open_meteo_weather import fetch_open_meteo_weather, render_open_meteo_reply
        requests = types.SimpleNamespace(get=lambda url, **kw: (
            fake_response(payload=GEOCODED_ODEMIS)
            if "geocoding" in url else
            fake_response(payload=valid_meteo_payload(forecast=True))
        ))
        source = fetch_open_meteo_weather(
            "Ödemiş", get=requests.get, forecast=True,
        )
        answer = render_open_meteo_reply("İzmir Ödemiş hava tahminleri", source)
        self.assertIn("3 günlük", answer)
        self.assertIn("11.3", answer)
        self.assertIn("22.3", answer)
        self.assertEqual(3, answer.count("en düşük"))
        self.assertIn("Open-Meteo", answer)

    def test_weather_rejects_stale_or_partial_or_nonmatching_geo_without_fabrication(self):
        from core.open_meteo_weather import fetch_open_meteo_weather, render_open_meteo_reply
        def source(geo, data):
            def get(url, **kwargs):
                return fake_response(payload=geo if "geocoding" in url else data)
            return fetch_open_meteo_weather("Ödemiş", get=get, forecast=False)
        self.assertIsNone(source({"results": [{"name": "Bergama", "country_code": "TR",
                                                  "latitude": 38.0, "longitude": 27.0}]},
                                 valid_meteo_payload()))
        self.assertIsNone(source(GEOCODED_ODEMIS, valid_meteo_payload(old=True)))
        bad = valid_meteo_payload()
        bad["current"]["temperature_2m"] = 500
        self.assertIsNone(source(GEOCODED_ODEMIS, bad))
        bad = valid_meteo_payload()
        bad["current_units"]["temperature_2m"] = "°F"
        self.assertIsNone(source(GEOCODED_ODEMIS, bad))
        self.assertIsNone(render_open_meteo_reply(
            "Ödemiş hava durumu", "OPEN_METEO_JSON:<script>alert(1)</script>"
        ))

    def test_backup_rejects_unverified_location_and_mismatched_city(self):
        from core.open_meteo_weather import fetch_open_meteo_weather, render_open_meteo_reply
        def get(url, **kwargs):
            return fake_response(payload=(
                GEOCODED_ODEMIS if "geocoding" in url else valid_meteo_payload()
            ))
        source = fetch_open_meteo_weather("Ödemiş", get=get)
        self.assertIsNone(render_open_meteo_reply("Ankara hava durumu", source))
        self.assertIsNone(fetch_open_meteo_weather("<script>", get=get))
        self.assertIsNone(fetch_open_meteo_weather("", get=get))

    def test_cano_direct_router_accepts_validated_open_meteo_without_llm(self):
        from core.weather_reliability import weather_direct_reply
        from core.open_meteo_weather import fetch_open_meteo_weather
        def get(url, **kwargs):
            return fake_response(payload=(
                GEOCODED_ODEMIS if "geocoding" in url else valid_meteo_payload()
            ))
        source = fetch_open_meteo_weather("Ödemiş", get=get)
        answer = weather_direct_reply("İzmir Ödemiş hava durumu", source)
        self.assertIn("Open-Meteo", answer)
        self.assertIn("18.4", answer)
        self.assertNotIn("Crossref", answer)
        self.assertNotIn("LLM", answer)


if __name__ == "__main__":
    unittest.main()
