"""Cross-platform, stdlib-only checks for adaptation report no-clobber writes."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from organism_lab_cloud.organism_lab.adaptation_study import save_adaptation_study


class AdaptationReportCrossPlatformTests(unittest.TestCase):
    def test_existing_report_is_immutable_and_identical_retry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence" / "report.json"
            first = {"run": "A", "value": 1}
            different = {"run": "B", "value": 2}
            self.assertEqual(save_adaptation_study(first, path), path)
            snapshot = path.read_bytes()
            self.assertEqual(save_adaptation_study(first, path), path)
            self.assertEqual(path.read_bytes(), snapshot)
            with self.assertRaises(FileExistsError):
                save_adaptation_study(different, path)
            self.assertEqual(path.read_bytes(), snapshot)

    def test_simultaneous_distinct_runs_never_clobber_each_other(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            runs = ({"run": "A", "value": 1}, {"run": "B", "value": 2})
            barrier = threading.Barrier(2)

            def writer(report):
                barrier.wait(timeout=10)
                try:
                    save_adaptation_study(report, path)
                    return "saved"
                except FileExistsError:
                    return "collision"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(writer, runs))
            self.assertCountEqual(outcomes, ["saved", "collision"])
            self.assertIn(json.loads(path.read_text(encoding="utf-8")), runs)


if __name__ == "__main__":
    unittest.main()
