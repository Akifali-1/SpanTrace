from __future__ import annotations

from typing import Any


TRANSPORT_OPTIONS: dict[str, list[dict[str, Any]]] = {
    "Lisbon": [
        {"id": "TRAIN-EXPRESS", "mode": "train", "price_cents": 72000, "duration_hours": 3.5},
        {"id": "TRAIN-SAVER", "mode": "train", "price_cents": 40000, "duration_hours": 5.0},
    ]
}

ACCOMMODATION_OPTIONS: dict[str, list[dict[str, Any]]] = {
    "Lisbon": [
        {"id": "HOTEL-CENTRAL", "name": "Central Harbor Hotel", "preference": "central", "nightly_price_cents": 50000},
        {"id": "HOTEL-SAVER", "name": "Garden Saver Inn", "preference": "budget", "nightly_price_cents": 40000},
    ]
}

ACTIVITY_OPTIONS: dict[str, list[dict[str, Any]]] = {
    "Lisbon": [
        {"id": "ACT-MUSEUM", "category": "culture", "name": "Tile Museum", "price_cents": 18000},
        {"id": "ACT-FOOD", "category": "food", "name": "Market Tasting", "price_cents": 12000},
        {"id": "ACT-PARK", "category": "outdoors", "name": "Riverside Park", "price_cents": 10000},
    ]
}


def fixture_for(scenario: str) -> dict[str, Any]:
    common = {
        "destination": "Lisbon",
        "start_date": "2026-06-10",
        "end_date": "2026-06-13",
        "travelers": 2,
        "accommodation_preference": "central",
        "activity_preferences": ["culture", "food"],
    }
    budgets = {"success": 300000, "bug": 240000, "adjustment": 150000}
    if scenario not in budgets:
        raise ValueError(f"unknown scenario: {scenario}")
    return {**common, "budget_cents": budgets[scenario], "scenario": scenario}
