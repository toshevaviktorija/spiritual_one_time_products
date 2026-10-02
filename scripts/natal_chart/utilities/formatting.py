"""Formatting and escaping helpers."""

from __future__ import annotations

import re
from html import escape
from typing import Any, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")


def xml_text(value: Any) -> str:
    return escape("" if value is None else str(value)).replace("\n", "<br/>")


def display_name(value: Any) -> str:
    return str(value or "-").replace("_", " ").strip().title()


def format_degrees(value: Any, fallback: str = "-") -> str:
    try:
        decimal = abs(float(value))
    except (TypeError, ValueError):
        return fallback
    degree = int(decimal)
    minute = int(round((decimal - degree) * 60))
    if minute == 60:
        degree, minute = degree + 1, 0
    return f"{degree}\u00b0 {minute:02d}\u2032"


def chunked(items: Sequence[T], size: int) -> Iterator[Sequence[T]]:
    safe_size = max(1, size)
    for index in range(0, len(items), safe_size):
        yield items[index:index + safe_size]


def safe_filename(value: str, fallback: str = "Unknown_Person") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_")
    return cleaned or fallback


def compact(items: Iterable[Any]) -> list[Any]:
    return [item for item in items if item not in (None, "")]
