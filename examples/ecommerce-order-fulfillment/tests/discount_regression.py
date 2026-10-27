from __future__ import annotations

import pathlib
import sys
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from pricing import apply_discount  # noqa: E402


class DiscountRegressionTests(unittest.TestCase):
    def test_spring_discount_is_applied_once(self):
        self.assertEqual(apply_discount(6500, "SPRING20")["total_cents"], 5200)


if __name__ == "__main__":
    unittest.main()
