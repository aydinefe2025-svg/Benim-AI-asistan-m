"""Guard PG16/PG18 CI client installs against avoidable external-key outages."""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/postgres-restore-rehearsal.yml"


class PostgresRehearsalClientInstallTests(unittest.TestCase):
    def test_runner_pinned_during_ubuntu_26_migration(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("runs-on: ubuntu-24.04", text)

    def test_pg16_uses_native_ubuntu_package_without_pgdg_key_download(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('if [[ "${PG_MAJOR}" == "16" ]]; then', text)
        self.assertIn("sudo apt-get install -y -qq postgresql-client-16", text)
        self.assertIn("else\n", text)
        native = text.split('if [[ "${PG_MAJOR}" == "16" ]]; then', 1)[1].split("\n          else\n", 1)[0]
        self.assertNotIn("curl", native)
        self.assertNotIn("apt.postgresql.org", native)

    def test_pgdg_key_download_retries_only_for_pg18(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("curl --retry 4 --retry-all-errors", text)
        self.assertIn("postgresql-client-${PG_MAJOR}", text)
        self.assertLess(text.index("curl --retry 4 --retry-all-errors"), text.index('postgresql-client-${PG_MAJOR}'))


if __name__ == "__main__":
    unittest.main()
