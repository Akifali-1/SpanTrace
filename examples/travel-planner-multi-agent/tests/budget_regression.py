from __future__ import annotations

import pathlib
import sys
import unittest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parents[1] / "packages" / "python-sdk"))

from budget_agent import calculate_budget  # noqa: E402
from fixtures import fixture_for  # noqa: E402
from models import TripRequest  # noqa: E402
from transport_agent import lookup_transport_tool  # noqa: E402
from accommodation_agent import lookup_accommodation_tool  # noqa: E402
from activities_agent import lookup_activities_tool  # noqa: E402


class BudgetRegressionTests(unittest.TestCase):
    def test_transport_remains_in_cents_during_aggregation(self):
        request = TripRequest.from_inputs(fixture_for("bug"))
        transport = {"price_cents": lookup_transport_tool(request)[0]["price_cents"]}
        accommodation_option = lookup_accommodation_tool(request)[0]
        accommodation = {"total_cents": accommodation_option["nightly_price_cents"] * request.nights}
        activities = {"total_cents": sum(item["price_cents"] for item in lookup_activities_tool(request))}
        result = calculate_budget(request, transport, accommodation, activities)
        self.assertEqual(result["reported_total_cents"], 252000)
        self.assertEqual(result["decision"], "over_budget")


if __name__ == "__main__":
    unittest.main()
