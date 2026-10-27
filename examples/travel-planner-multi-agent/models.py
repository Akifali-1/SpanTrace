from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TripRequest:
    destination: str
    start_date: date
    end_date: date
    travelers: int
    budget_cents: int
    accommodation_preference: str
    activity_preferences: tuple[str, ...]
    scenario: str = "success"

    @property
    def nights(self) -> int:
        return (self.end_date - self.start_date).days

    @classmethod
    def from_inputs(cls, values: dict[str, Any]) -> "TripRequest":
        start = date.fromisoformat(str(values["start_date"]))
        end = date.fromisoformat(str(values["end_date"]))
        if end <= start:
            raise ValueError("end_date must be after start_date")
        if int(values.get("travelers", 0)) <= 0:
            raise ValueError("travelers must be positive")
        preferences = tuple(str(item) for item in values.get("activity_preferences", ()))
        return cls(
            destination=str(values["destination"]),
            start_date=start,
            end_date=end,
            travelers=int(values["travelers"]),
            budget_cents=int(values["budget_cents"]),
            accommodation_preference=str(values.get("accommodation_preference", "central")),
            activity_preferences=preferences,
            scenario=str(values.get("scenario", "success")),
        )
