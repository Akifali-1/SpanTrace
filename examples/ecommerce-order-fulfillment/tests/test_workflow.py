from __future__ import annotations

import pathlib
import sys
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import main  # noqa: E402


class OrderWorkflowTests(unittest.TestCase):
    def test_success_fixture_confirms_order(self):
        result = main({"scenario": "success"})
        self.assertTrue(result["confirmed"])
        self.assertEqual(result["subtotal_cents"], 6500)
        self.assertEqual(result["total_cents"], 5850)

    def test_unknown_scenario_is_rejected(self):
        with self.assertRaises(ValueError):
            main({"scenario": "unknown"})


if __name__ == "__main__":
    unittest.main()
