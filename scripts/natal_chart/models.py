"""Validated, normalized access to natal chart API data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping


@dataclass(frozen=True)
class ChartPoint:
    key: str
    data: Mapping[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("name") or self.key).replace("_", " ")

    @property
    def has_interpretation(self) -> bool:
        return any(self.data.get(key) for key in ("life_area", "description", "sign_meaning", "house_meaning"))


@dataclass(frozen=True)
class NatalChartData:
    subject: Mapping[str, Any]
    chart: Mapping[str, Any]
    user: Mapping[str, Any]
    metadata: Mapping[str, Any]
    premium_aggregates: Mapping[str, Any]
    aspects: tuple[Mapping[str, Any], ...] = ()
    patterns: tuple[Mapping[str, Any], ...] = ()
    interpretation_text: Mapping[str, Any] | str = ""
    created_at: str = ""

    @classmethod
    def from_file(cls, path: Path) -> "NatalChartData":
        with path.open(encoding="utf-8") as stream:
            return cls.from_mapping(json.load(stream))

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "NatalChartData":
        api_data = payload.get("data", payload)
        if not isinstance(api_data, Mapping):
            raise ValueError("Expected the JSON 'data' field to be an object")
        response = api_data.get("fullApiResponse", api_data)
        if not isinstance(response, Mapping):
            raise ValueError("Expected 'fullApiResponse' to be an object")
        subject = response.get("subject_data")
        chart = response.get("chart_data")
        if not isinstance(subject, Mapping) or not isinstance(chart, Mapping):
            raise ValueError("Natal chart JSON must contain subject_data and chart_data objects")
        premium = api_data.get("aggregatesPremium") or response.get("aggregatesPremium") or {}
        aggregates = premium.get("aggregates", premium) if isinstance(premium, Mapping) else {}
        aspects = api_data.get("aspects", response.get("aspects", []))
        if not isinstance(aspects, list) or any(not isinstance(item, Mapping) for item in aspects):
            raise ValueError("Expected aspects to be a list of objects")
        for item in aspects:
            for key in ("point1", "point2", "aspect", "interpretation"):
                if not isinstance(item.get(key), Mapping):
                    raise ValueError(f"Aspect {key} must be an object")
        patterns = api_data.get("patterns", response.get("patterns", []))
        if not isinstance(patterns, list) or any(not isinstance(item, Mapping) for item in patterns):
            raise ValueError("Expected patterns to be a list of objects")
        for item in patterns:
            if not isinstance(item.get("interpretation"), Mapping):
                raise ValueError("Pattern interpretation must be an object")
        return cls(
            subject=subject,
            chart=chart,
            user=api_data.get("user") or {},
            metadata=chart.get("meta") or {},
            premium_aggregates=aggregates if isinstance(aggregates, Mapping) else {},
            aspects=tuple(aspects),
            patterns=tuple(patterns),
            interpretation_text=api_data.get("interpretationText", response.get("interpretationText")) or "",
            created_at=str(api_data.get("createdAt", response.get("createdAt")) or ""),
        )

    @property
    def name(self) -> str:
        return str(self.subject.get("name") or self.user.get("name") or "Unknown Person")

    def _named_points(self, list_key: str) -> Iterator[ChartPoint]:
        for raw_name in self.subject.get(list_key) or []:
            key = str(raw_name).lower()
            value = self.subject.get(key)
            if isinstance(value, Mapping):
                yield ChartPoint(key, value)

    @property
    def planets(self) -> list[ChartPoint]:
        return list(self._named_points("planets_names_list"))

    @property
    def angles(self) -> list[ChartPoint]:
        return list(self._named_points("axial_cusps_names_list"))

    @property
    def houses(self) -> list[ChartPoint]:
        return list(self._named_points("houses_names_list"))

    @property
    def interpreted_planets(self) -> list[ChartPoint]:
        return [point for point in self.planets if point.has_interpretation]

    @property
    def interpreted_angles(self) -> list[ChartPoint]:
        return [point for point in self.angles if point.has_interpretation]

    @property
    def interpreted_houses(self) -> list[ChartPoint]:
        return [point for point in self.houses if point.has_interpretation]

    @property
    def wheel_positions(self) -> list[Mapping[str, Any]]:
        points = [point.data for point in (*self.planets, *self.angles) if point.data.get("abs_pos") is not None]
        return points or list(self.chart.get("planetary_positions") or [])
