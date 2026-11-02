import json
import tempfile
import unittest
from pathlib import Path
from scripts.daily_research import run, TOPICS

class DailyResearchTests(unittest.TestCase):
    def test_archives_all_topics_with_source_links(self):
        def fake(url):
            return {"query": {"pages": {"1": {
                "title": "Neutron star",
                "fullurl": "https://en.wikipedia.org/wiki/Neutron_star"
            }}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = run(fetch=fake, output_dir=tmp)
            report = json.loads(Path(path).read_text(encoding="utf-8"))
            self.assertEqual(set(report["topics"]), set(TOPICS))
            self.assertFalse(report["verified"])
            self.assertTrue(all(v["status"] == "found" for v in report["topics"].values()))

    def test_failures_recorded_without_losing_other_topics(self):
        def broken(url):
            raise OSError("offline")
        with tempfile.TemporaryDirectory() as tmp:
            report = json.loads(run(fetch=broken, output_dir=tmp).read_text(encoding="utf-8"))
            self.assertTrue(all(v["status"] == "error" for v in report["topics"].values()))
            self.assertTrue(all(v["error_type"] == "OSError" for v in report["topics"].values()))

if __name__ == "__main__":
    unittest.main()
