from __future__ import annotations

import pathlib
import sys
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from main import main  # noqa: E402


class TravelPlannerWorkflowTests(unittest.TestCase):
    def test_success_fixture_is_valid(self):
        result = main({"scenario": "success"})
        self.assertTrue(result["validation"]["valid"])
        self.assertEqual(result["validation"]["actual_total_cents"], 252000)
        self.assertEqual(result["budget"]["reported_total_cents"], 252000)
        self.assertTrue(result["validation"]["reported_total_consistent"])
        self.assertEqual(result["itinerary"]["budget_decision"], "within_budget")

    def test_adjustment_fixture_reaches_explicit_failure(self):
        with self.assertRaises(AssertionError):
            main({"scenario": "adjustment"})


if __name__ == "__main__":
    unittest.main()
