import tempfile
import unittest
from pathlib import Path

import ci_smoke


class SmokeTests(unittest.TestCase):
    def test_reproducible_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            outcome = ci_smoke.check(Path(d) / 'research')
            self.assertEqual(outcome['replay_inserted'], 0)
            self.assertEqual(outcome['replay_skipped'], 1977)
            self.assertEqual(outcome['audit']['checked'], 1977)


if __name__ == '__main__':
    unittest.main()