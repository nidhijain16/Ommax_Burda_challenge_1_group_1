"""Registry tests for src/data_loader.py. Run: python -m unittest discover -s tests"""

import csv
import os
import sys
import unittest

CHALLENGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CHALLENGE_DIR not in sys.path:
    sys.path.insert(0, CHALLENGE_DIR)

from src.data_loader import DataLoader  # noqa: E402

DATA_DIR = os.path.join(CHALLENGE_DIR, "data")


class TestRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = DataLoader(DATA_DIR)

    def test_opportunity_space_m002_resolves(self):
        rec = self.loader.by_id.get("M002")
        self.assertIsNotNone(rec)
        self.assertEqual(rec["_table"], "spaces")
        self.assertEqual(rec["topic_key"], "care_elderly")

    def test_all_opportunity_spaces_resolve(self):
        with open(os.path.join(DATA_DIR, "09_opportunity_spaces.csv"), encoding="utf-8") as f:
            ids = [r["context_id"] for r in csv.DictReader(f)]
        self.assertGreater(len(ids), 0)
        for sid in ids:
            self.assertIn(sid, self.loader.by_id, sid)
            self.assertEqual(self.loader.by_id[sid]["_table"], "spaces")


if __name__ == "__main__":
    unittest.main()
