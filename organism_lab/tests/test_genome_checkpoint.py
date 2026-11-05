import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from organism_lab.genome_checkpoint import (
    _replay, _serialize, advance_checkpoint, initialize_checkpoint, read_checkpoint
)


class GenomeCheckpointTests(unittest.TestCase):
    def test_restart_exact_state_and_idempotent_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "state.json"
            start = initialize_checkpoint(file, seed=22, target_tick=15)
            self.assertEqual(start["ticks"], 15)
            after = advance_checkpoint(file, target_tick=40)
            expected = _replay(start["parameters"], 40)
            self.assertEqual(after["state"]["metrics"], expected.metrics())
            self.assertEqual(len(after["state"]["organisms"]), len(expected.organisms))
            before_bytes = file.read_bytes()
            self.assertEqual(advance_checkpoint(file, target_tick=40), after)
            self.assertEqual(file.read_bytes(), before_bytes)
            self.assertEqual(read_checkpoint(file), after)

    def test_rejects_tampered_state_with_original_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "state.json"
            initialize_checkpoint(file, seed=3, target_tick=20)
            doc = json.loads(file.read_text())
            doc["state"]["metrics"]["births"] = 999
            file.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                read_checkpoint(file)

    def test_rejects_forged_valid_digest_but_impossible_state(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "state.json"
            initialize_checkpoint(file, seed=3, target_tick=20)
            doc = json.loads(file.read_text())
            doc["state"]["metrics"]["births"] = 999
            body = {k: doc[k] for k in ("schema", "parameters", "ticks", "state")}
            doc["sha256"] = hashlib.sha256(_serialize(body)).hexdigest()
            file.write_text(json.dumps(doc))
            with self.assertRaisesRegex(ValueError, "deterministic replay"):
                read_checkpoint(file)

    def test_refuses_overwrite_rollback_and_unbounded_ticks(self):
        with tempfile.TemporaryDirectory() as temp:
            file = Path(temp) / "state.json"
            initialize_checkpoint(file, target_tick=10)
            with self.assertRaises(FileExistsError):
                initialize_checkpoint(file)
            with self.assertRaises(ValueError):
                advance_checkpoint(file, target_tick=9)
            with self.assertRaises(ValueError):
                advance_checkpoint(file, target_tick=10001)
            self.assertEqual(read_checkpoint(file)["ticks"], 10)


if __name__ == "__main__":
    unittest.main()
