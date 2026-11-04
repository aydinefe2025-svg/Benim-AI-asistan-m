"""Prevent Vercel from treating the Streamlit entrypoint as a WSGI app.

Vercel owns only a static link to the separately deployed Render application.
No backend credentials or production application code are exposed here.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDER_APP = "https://benim-ai-asistan-streamlit.onrender.com/"


class VercelStaticGatewayTests(unittest.TestCase):
    def test_explicit_builder_excludes_python_streamlit(self):
        data = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
        self.assertEqual(data["builds"], [{"src": "index.html", "use": "@vercel/static"}])
        self.assertFalse(any("python" in str(x).lower() for x in data["builds"]))
        self.assertEqual(data["routes"], [{"src": "/", "dest": "/index.html"}])

    def test_public_gateway_is_plain_html_link_to_live_render(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn(RENDER_APP, html)
        self.assertIn('lang="tr"', html)
        self.assertNotIn("<script", html.casefold())
        self.assertNotIn("GROQ_API_KEY", html)
        self.assertNotIn("DATABASE_URL", html)
        self.assertNotIn("APP_AUTH_REQUIRED", html)


if __name__ == "__main__":
    unittest.main()
