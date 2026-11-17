import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CanoChatNavigationTests(unittest.TestCase):
    def test_main_entrypoint_advertises_chat_before_login_gate(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('st.set_page_config(page_title="CANO Sohbet", page_icon="💬", layout="wide")', source)
        link = 'st.sidebar.page_link("app.py", label="CANO Sohbet", icon="💬")'
        self.assertIn(link, source)
        self.assertLess(source.index(link), source.index("_OWNER_KEY = render_auth_gate"))

    def test_evidence_page_links_back_to_chat_before_login_gate(self):
        source = (ROOT / "pages" / "01_CANO_Kaynak_Denetimi.py").read_text(encoding="utf-8")
        link = 'st.page_link("app.py", label="CANO Sohbet", icon="💬")'
        self.assertIn(link, source)
        self.assertLess(source.index(link), source.index("owner = render_auth_gate"))

    def test_chat_and_fail_closed_auth_remain(self):
        app = (ROOT / "app.py").read_text(encoding="utf-8")
        auth = (ROOT / "core" / "authentication.py").read_text(encoding="utf-8")
        self.assertIn('st.chat_input("Asistanınıza dilediğiniz her şeyi sorun...")', app)
        self.assertIn("_OWNER_KEY = render_auth_gate(st, os.environ)", app)
        self.assertIn("st.stop()", auth)
