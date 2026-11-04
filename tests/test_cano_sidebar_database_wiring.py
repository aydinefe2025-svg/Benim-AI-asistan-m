"""App integration contract: sidebar colony and CANO cockpit share owner and DB.

This is a static contract test because importing app.py runs the live
Streamlit/OIDC entrypoint and may accidentally contact production services.
"""
import ast
from pathlib import Path
import unittest


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _call_kwargs(target):
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == target
    ]
    if len(calls) != 1:
        raise AssertionError(f"Expected one {target} call, found {len(calls)}")
    return {kw.arg: ast.unparse(kw.value) for kw in calls[0].keywords}


class CanoSidebarOwnerDatabaseWiringTests(unittest.TestCase):
    def test_sidebar_restores_same_verified_cano_owner_and_database_as_cockpit(self):
        cockpit = _call_kwargs("render_cano_command_center")
        sidebar = _call_kwargs("render_colony_panel")
        self.assertEqual(
            sidebar["owner_key"], cockpit["owner_key"],
            "Sidebar restore must not depend on an unrelated general-memory store")
        self.assertEqual(
            sidebar["database_url"], cockpit["database_url"],
            "Sidebar restore must use exactly the same CANO database as mission saves")

    def test_cano_database_requires_authenticated_owner(self):
        cockpit = _call_kwargs("render_cano_command_center")
        self.assertEqual(cockpit["owner_key"], "_CANO_OWNER_KEY")
        self.assertEqual(
            cockpit["database_url"],
            "cano_database_url(os.environ) if _CANO_OWNER_KEY else None")


if __name__ == "__main__":
    unittest.main()
