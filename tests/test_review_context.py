"""Guard against silently dropping reviewer feedback from model input."""
import ast
import unittest
from pathlib import Path


class ReviewContextTests(unittest.TestCase):
    def test_research_answer_keeps_long_review_context(self):
        source = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        fn = next(node for node in tree.body
                  if isinstance(node, ast.FunctionDef) and node.name == "_research_answer")
        segments = [node for node in ast.walk(fn)
                    if isinstance(node, ast.Subscript)
                    and isinstance(node.value, ast.Name) and node.value.id == "goal"]
        self.assertTrue(any(isinstance(n.slice, ast.Slice)
                            and isinstance(n.slice.upper, ast.Constant)
                            and n.slice.upper.value >= 24000 for n in segments))


if __name__ == "__main__":
    unittest.main()
