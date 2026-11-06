"""Prevent scheduled colony CI import errors before it can save durable state."""
from pathlib import Path
import unittest


class ColonyCycleWorkflowDependenciesTests(unittest.TestCase):
    def test_secure_backup_dependency_is_installed_before_colony_regressions(self):
        root = Path(__file__).resolve().parents[1]
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("cryptography>=44,<51", requirements)
        workflow = (root / ".github/workflows/cano-colony-cycle.yml").read_text(
            encoding="utf-8"
        )
        install_step = 'run: python -m pip install "cryptography>=44,<51"'
        self.assertIn(install_step, workflow)
        self.assertLess(
            workflow.index(install_step),
            workflow.index("Check colony regressions before writing state"),
        )


if __name__ == "__main__":
    unittest.main()
