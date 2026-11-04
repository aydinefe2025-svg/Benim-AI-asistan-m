"""Non-invasive Playwright smoke of CANO's live Streamlit public entry points.

No login, model calls, mutations, or personal account data are performed.
A login-gated route is an explicit partial result, never a source-audit E2E pass.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright

BASE = os.environ.get(
    "CANO_PUBLIC_URL", "https://benim-ai-asistan-streamlit.onrender.com"
).rstrip("/") + "/"
FATAL = (
    "An error has occurred while running this app",
    "Traceback (most recent call last)",
    "Güvenli giriş yapılandırılmamış",
    "Kalıcı hafıza bağlantısı kurulamadı",
    "Model bağlantısı için Streamlit Secrets",
)


def inspect(page, path):
    url = urljoin(BASE, path)
    errors = []
    page.on("pageerror", lambda err: errors.append(str(err)))
    response = page.goto(url, wait_until="domcontentloaded", timeout=120000)
    if response is None or response.status >= 400:
        raise AssertionError(f"HTTP failure on {path}: {response.status if response else 'no response'}")
    page.wait_for_function(
        """() => {
          const s = document.body?.innerText || '';
          // A sidebar-only Streamlit shell contains "CANO" before page hydration.
          // Wait for actual page content or a decisive startup error.
          return /Giriş gerekli|CANO Komuta Merkezi|CANO Kaynak–İddia Denetimi|CANO — Yapay Zekâ Komuta Merkezi|Güvenli giriş yapılandırılmamış|Kalıcı hafıza bağlantısı kurulamadı|An error has occurred|Traceback/.test(s);
        }""", timeout=90000,
    )
    visible = page.locator("body").inner_text(timeout=20000)
    for bad in FATAL:
        if bad in visible:
            raise AssertionError(f"Application startup error on {path}: {bad}")
    if errors:
        raise AssertionError(f"Browser JavaScript error on {path}: {errors[:2]}")
    login_gate = "Giriş gerekli" in visible
    source_page = "CANO Kaynak–İddia Denetimi" in visible
    command_center = ("CANO Komuta Merkezi" in visible or
                      "CANO — Yapay Zekâ Komuta Merkezi" in visible)
    if not (login_gate or source_page or command_center):
        raise AssertionError("Expected CANO page or explicit authentication gate; public text: " + repr(visible[:450]))
    return {
        "path": path or "/",
        "http_status": response.status,
        "login_gate": login_gate,
        "source_page_visible": source_page,
        "command_center_visible": command_center,
        "user_authenticated": False,
        "model_calls": 0,
        "scientific_claims_verified": 0,
    }


def main():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(locale="tr-TR")
            root = inspect(context.new_page(), "")
            evidence = inspect(context.new_page(), "CANO_Kaynak_Denetimi")
            print(json.dumps({
                "checks": [root, evidence],
                "scope": "public-browser-smoke-only",
                "private_authenticated_source_clickthrough": "not_tested",
            }, ensure_ascii=False))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
