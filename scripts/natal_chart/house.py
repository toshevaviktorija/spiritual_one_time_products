"""Reusable presentation pattern for one astrological house."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from .constants import HOUSE_SHORT_INFO, PLANET_SYMBOLS, ROMAN_HOUSES, SIGN_NAMES
from .flowables import PanelTable, panel_box_style, ZodiacSignBadge, color
from .models import ChartPoint
from .utilities.formatting import xml_text


@dataclass(frozen=True)
class HousePattern:
    """Build a spacious, null-safe house profile for paired house pages."""

    number: int
    house: Mapping[str, Any]
    meaning: Mapping[str, Any]
    planets: Sequence[ChartPoint]
    styles: Mapping[str, ParagraphStyle]
    palette: Mapping[str, str]
    symbol_font: str
    panel_width: float

    def _title(self) -> str:
        return str(self.meaning.get("title") or self.house.get("name") or f"House {self.number}").replace("_", " ")

    def _position(self) -> str:
        try:
            return f"{float(self.house.get('position')):.1f}°"
        except (TypeError, ValueError):
            return ""

    def _overview(self) -> Table:
        sign_key = str(self.house.get("sign") or "")
        sign_name = SIGN_NAMES.get(sign_key, sign_key or "-")
        symbol = str(self.house.get("emoji") or "")
        badge = ZodiacSignBadge(sign_key, symbol, self.symbol_font, 9 * mm)
        left = [
            Paragraph(f"HOUSE {ROMAN_HOUSES[self.number - 1]}", self.styles["house_roman"]),
            Paragraph(xml_text(str(self.meaning.get("life_area") or self.house.get("life_area") or "")), self.styles["house_meta"]),
        ]
        padding = 4 * mm
        inner_width = self.panel_width - 2 * padding
        right_width = inner_width * 0.48
        right_heading = Table([[
            badge,
            Paragraph(f"{xml_text(sign_name.upper())}&nbsp;&nbsp;{xml_text(self._position())}", self.styles["house_sign"]),
        ]], colWidths=[10.5 * mm, right_width - 10.5 * mm])
        right_heading.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        traits = "  ·  ".join(str(value) for value in (self.house.get("quality"), self.house.get("element")) if value)
        right = [right_heading, Spacer(1, 2 * mm), Paragraph(xml_text(traits), self.styles["house_traits"])]
        overview = Table([[left, right]], colWidths=[inner_width * 0.52, right_width])
        overview.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (0, 0), 3 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        content: list[Any] = [overview]
        description = self.meaning.get("description") or self.house.get("description")
        if description is not None and str(description).strip():
            content.extend([Spacer(1, 3 * mm), Paragraph(xml_text(str(description)), self.styles["house_description"])])
        panel = PanelTable([[content]], colWidths=[self.panel_width], hAlign="CENTER")
        panel.setStyle(TableStyle([
            *panel_box_style(self.palette),
            ("CORNERARTWORK", self.palette["corner_artwork"], 16 * mm),
            ("LEFTPADDING", (0, 0), (-1, -1), padding), ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ]))
        return panel

    def _planet_line(self) -> Paragraph | None:
        house_name = self.house.get("name")
        occupants = [point for point in self.planets if point.data.get("house") == house_name]
        if not occupants:
            return None
        entries = []
        for point in occupants:
            symbol = PLANET_SYMBOLS.get(point.name, "•")
            try:
                degrees = f"{float(point.data.get('position')):.1f}°"
            except (TypeError, ValueError):
                degrees = ""
            entries.append(f"<font name='{self.symbol_font}'>{xml_text(symbol)}</font> {xml_text(point.name)} {degrees}".strip())
        return Paragraph("&nbsp;&nbsp;·&nbsp;&nbsp;".join(entries), self.styles["house_planets"])

    def build(self) -> list[Any]:
        sign_meaning = self.house.get("sign_meaning")
        story: list[Any] = [
            Paragraph(xml_text(self._title()), self.styles["house_title"]),
            Spacer(1, 0.9 * mm),
            Paragraph(xml_text(str(self.meaning.get("short_title") or HOUSE_SHORT_INFO[self.number])), self.styles["house_subtitle"]),
            Spacer(1, 3.5 * mm),
            self._overview(),
        ]
        if sign_meaning:
            story.extend([
                Spacer(1, 3.5 * mm),
                Paragraph(xml_text(str(sign_meaning)), self.styles["house_body"]),
            ])
        planet_line = self._planet_line()
        if planet_line is not None:
            story.extend([
                Spacer(1, 1.9 * mm),
                HRFlowable(width="100%", thickness=0.45, color=color(self.palette["gold_light"])),
                Spacer(1, 1.9 * mm),
                planet_line,
            ])
        return story
