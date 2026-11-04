"""Regression checks for the explicit, owner-scoped evidence-page restore gate."""
import ast
import unittest
from pathlib import Path


PAGE = Path(__file__).resolve().parents[1] / "pages" / "01_CANO_Kaynak_Denetimi.py"


class EvidencePageOwnerRestoreTests(unittest.TestCase):
    def test_page_requires_explicit_authenticated_owner_restore(self):
        tree = ast.parse(PAGE.read_text(encoding="utf-8"))
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        restores = [node for node in calls
                    if isinstance(node.func, ast.Name)
                    and node.func.id == "restore_owner_backup"]
        self.assertEqual(len(restores), 1)
        self.assertTrue(any(k.arg == "approved" and isinstance(k.value, ast.Constant)
                            and k.value.value is True for k in restores[0].keywords))
        text = PAGE.read_text(encoding="utf-8")
        self.assertIn('if owner and not local_agent_count:', text)
        self.assertIn('if st.button("Hesabıma ait CANO yedeğini geri yükle"', text)
        self.assertIn('st.rerun()', text)
        self.assertIn('st.stop()', text)
        self.assertIn('render_auth_gate(st, os.environ)', text)

    def test_owner_restore_never_writes_over_nonempty_colony(self):
        from tempfile import TemporaryDirectory
        from core.agent_colony import AgentColony
        from core.colony_restore import restore_empty_colony

        with TemporaryDirectory() as tmp:
            colony = AgentColony(Path(tmp) / "test.sqlite3")
            colony.create_founder("research", "Research")
            with self.assertRaisesRegex(RuntimeError, "empty colony"):
                restore_empty_colony(colony, {
                    "agents": [], "feedback": [], "reviews": [], "missions": []})


if __name__ == "__main__":
    unittest.main()
