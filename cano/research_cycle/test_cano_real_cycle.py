import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import cano_real_cycle as c


class CanoRealCycleTests(unittest.TestCase):
    def test_real_datasets(self):
        from sklearn.datasets import load_digits, load_wine
        for name, loader, expected in [('digits', load_digits, 1797), ('wine', load_wine, 178)]:
            X, y, hashes, result = c.dataset_records(name, loader())
            self.assertEqual(len(X), expected)
            self.assertEqual(len(set(hashes)), expected)
            self.assertTrue(result['scores']['model']['mean_accuracy'] > result['scores']['baseline']['mean_accuracy'])

    def test_reject_nonfinite(self):
        X = np.ones((10, 2))
        X[0, 0] = float('nan')
        with self.assertRaises(ValueError):
            c.validate_data(X, np.array([0]*5+[1]*5))

    def test_reject_duplicate_rows(self):
        X = np.arange(20, dtype=float).reshape(10, 2)
        X[1] = X[0]
        with self.assertRaises(ValueError):
            c.validate_data(X, np.array([0]*5+[1]*5))

    def test_real_end_to_end_replay_and_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'output'
            first = c.run_cycle(output)
            self.assertEqual(first['total_samples'], 1975)
            self.assertEqual(first['finding_count'], 1977)
            self.assertEqual(first['ingestion']['inserted'], 1977)
            self.assertTrue(c.verify_cycle(output)['ok'])
            second = c.run_cycle(output)
            self.assertEqual(second['ingestion']['already_processed'], 1977)
            self.assertEqual(second['ingestion']['inserted'], 0)
            self.assertTrue(c.verify_cycle(output)['ok'])
            path = output / 'wine_real_data.csv'
            path.write_bytes(path.read_bytes() + b'\nBOGUS')
            self.assertFalse(c.verify_cycle(output)['ok'])

    def test_fails_on_missing_or_unsafe_output(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(c.verify_cycle(Path(folder))['ok'])
            output = Path(folder) / 'out'
            output.symlink_to(folder, target_is_directory=True)
            with self.assertRaises(ValueError): c.run_cycle(output)

    def test_reject_scripted_symlink_swap(self):
        with tempfile.TemporaryDirectory() as folder:
            x = Path(folder)/'target'; x.write_text('safe')
            y = Path(folder)/'alias'; y.symlink_to(x)
            with self.assertRaises(ValueError): c.atomic_text(y, 'not safe')

if __name__ == '__main__': unittest.main()