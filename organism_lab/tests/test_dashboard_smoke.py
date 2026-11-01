"""Check dashboard source without importing Streamlit in CI."""
import ast
from pathlib import Path
import unittest

DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard.py"

class DashboardSmokeTests(unittest.TestCase):
    def test_dashboard_compiles(self):
        compile(DASHBOARD.read_text(encoding="utf-8"), str(DASHBOARD), "exec")

    def test_dashboard_calls_shared_world(self):
        tree = ast.parse(DASHBOARD.read_text(encoding="utf-8"))
        calls = [node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
        self.assertIn("run_shared_world", calls)

    def test_dashboard_contains_export_and_plot(self):
        tree = ast.parse(DASHBOARD.read_text(encoding="utf-8"))
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertIn("line_chart", attrs)
        self.assertIn("download_button", attrs)

if __name__ == "__main__":
    unittest.main()
