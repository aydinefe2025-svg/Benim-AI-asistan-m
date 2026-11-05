"""Concurrent-writer safety for replayable local genome checkpoints."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest

from organism_lab.genome_checkpoint import (
    advance_checkpoint, initialize_checkpoint, read_checkpoint
)


class GenomeCheckpointConcurrencyTests(unittest.TestCase):
    def test_concurrent_creation_allows_exactly_one_initializer(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "new" / "state.json"
            gate = Barrier(6)

            def initialize(_):
                gate.wait(timeout=10)
                try:
                    initialize_checkpoint(file, seed=11, target_tick=15)
                    return "created"
                except FileExistsError:
                    return "already_exists"

            with ThreadPoolExecutor(max_workers=6) as pool:
                outcomes = list(pool.map(initialize, range(6)))
            self.assertEqual(outcomes.count("created"), 1)
            self.assertEqual(outcomes.count("already_exists"), 5)
            self.assertEqual(read_checkpoint(file)["ticks"], 15)

    def test_concurrent_updates_never_overwrite_a_later_tick(self):
        with TemporaryDirectory() as folder:
            file = Path(folder) / "state.json"
            initialize_checkpoint(file, seed=12, target_tick=5)
            targets = (20, 35, 55, 80, 110)
            gate = Barrier(len(targets))

            def advance(target):
                gate.wait(timeout=10)
                try:
                    return advance_checkpoint(file, target_tick=target)["ticks"]
                except ValueError as exc:
                    self.assertIn("backwards", str(exc))
                    return None

            with ThreadPoolExecutor(max_workers=len(targets)) as pool:
                outcomes = list(pool.map(advance, targets))
            self.assertIn(110, outcomes)
            self.assertEqual(read_checkpoint(file)["ticks"], 110)
            self.assertEqual(advance_checkpoint(file, target_tick=110)["ticks"], 110)


if __name__ == "__main__":
    unittest.main()
