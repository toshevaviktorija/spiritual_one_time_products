"""Reusable presentation pattern for interpreted chart points."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table, TableStyle

from .constants import SIGN_NAMES, SIGN_RULERS
from .flowables import ProfileIcon, ZodiacSignBadge, color, translucent_color
from .utilities.formatting import xml_text


POINT_SYMBOLS = {
    "sun": "☉",
    "moon": "☽",
    "ascendant": "ASC",
    "medium_coeli": "MC",
    "mercury": "☿",
    "venus": "♀",
    "mars": "♂",
    "jupiter": "♃",
    "saturn": "♄",
    "mean_node": "☊",
    "mean_lilith": "LIL",
    "chiron": "CHI",
    "descendant": "DSC",
    "imum_coeli": "IC",
    "uranus": "♅",
    "neptune": "♆",
    "pluto": "♇",
}


@dataclass(frozen=True)
class PointPattern:
    """Build one consistent, null-safe chart-point profile."""

    key: str
    point: Mapping[str, Any]
    styles: Mapping[str, ParagraphStyle]
    palette: Mapping[str, str]
    symbol_font: str
    house_names: Sequence[str]
    panel_width: float
    title_override: str | None = None
    compact: bool = False
    intro_text: str | None = None
    intro_icon: str | None = None
    life_area_override: str | None = None

    def _house_number(self) -> int | str:
        house_name = self.point.get("house")
        return self.house_names.index(house_name) + 1 if house_name in self.house_names else "-"

    def _sign(self) -> tuple[str, str]:
        sign_key = str(self.point.get("sign") or "")
        return sign_key, SIGN_NAMES.get(sign_key, sign_key or "-")

    def _title(self) -> str:
        raw = self.title_override or str(self.point.get("name") or self.key).replace("_", " ")
        return raw.upper()

    def _point_heading(self) -> list[Any]:
        symbol = POINT_SYMBOLS.get(self.key, "●")
        title = self._title()
        symbol_size = 12 if self.compact else 14
        heading = f"<font name='{self.symbol_font}' size='{symbol_size}'>{xml_text(symbol)}</font>  {xml_text(title)}"
        return [Paragraph(heading, self.styles["title_type_2"])]

    def _position(self) -> str:
        try:
            degrees = f"{float(self.point.get('position')):.1f}°"
        except (TypeError, ValueError):
            degrees = ""
        parts = [value for value in (degrees, f"House {self._house_number()}") if value]
        return "  ·  ".join(parts)

    def _summary(self) -> list[Any]:
        spacing = 2.2 * mm if self.compact else 3.2 * mm
        summary = self._point_heading()
        life_area = self.life_area_override or self.point.get("life_area")
        if life_area:
            summary.extend([Spacer(1, 1.2 * mm), Paragraph(xml_text(str(life_area)), self.styles["small_info"])])
        summary.extend([
            Spacer(1, spacing),
            Paragraph(self._position(), self.styles["profile_position"]),
        ])
        return summary

    def _sign_panel(self) -> Table:
        sign_key, sign_name = self._sign()
        padding = 2.2 * mm if self.compact else 3.2 * mm
        zodiac_symbol = str(self.point.get("emoji") or "").replace("\ufe0f", "")
        traits = "  ·  ".join(
            str(value)
            for value in (self.point.get("element"), self.point.get("quality"), SIGN_RULERS.get(sign_key))
            if value
        )
        trait_size = 8.05 if self.compact else 8.7
        heading = (
            f"{xml_text(sign_name.upper())}"
            f"&nbsp;&nbsp;&nbsp;<font name='Times-Italic' size='{trait_size}' color='{self.palette['gold_light']}'>{xml_text(traits)}</font>"
        )
        badge_size = 7.2 * mm if self.compact else 8.2 * mm
        heading_row = Table([[
            ZodiacSignBadge(sign_key, zodiac_symbol, self.symbol_font, badge_size),
            Paragraph(heading, self.styles["point_sign_heading"]),
        ]], colWidths=[badge_size + 1.4 * mm, self.panel_width - 2 * padding - badge_size - 1.4 * mm])
        heading_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        content: list[Any] = [heading_row]
        description = self.point.get("description")
        if description is not None and str(description).strip():
            description_style = self.styles["point_sign_description_compact"] if self.compact else self.styles["point_sign_description"]
            content.extend([Spacer(1, 1.8 * mm), Paragraph(xml_text(str(description)), description_style)])
        panel = Table([[content]], colWidths=[self.panel_width], hAlign="CENTER")
        panel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), translucent_color(self.palette["panel_surface"], 0.52)),
            ("LINEBEFORE", (0, 0), (0, -1), 1.1, color(self.palette["gold"])),
            ("LEFTPADDING", (0, 0), (-1, -1), padding),
            ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ]))
        return panel

    def _interpretations(self) -> list[Any]:
        fields = (
            ("How it affects your sign", self.point.get("sign_meaning")),
            ("How it affects your house placement", self.point.get("house_meaning")),
        )
        available = [(title, value) for title, value in fields if value is not None and str(value).strip()]
        body_style = self.styles["point_detail_body_compact"] if self.compact else self.styles["point_detail_body"]
        spacing = 1.8 * mm if self.compact else 2.6 * mm
        content: list[Any] = []
        for index, (title, text) in enumerate(available):
            content.append(Spacer(1, spacing))
            if index:
                content.extend([
                    HRFlowable(width="100%", thickness=0.45, color=color(self.palette["gold_light"])),
                    Spacer(1, spacing),
                ])
            content.extend([
                Paragraph(xml_text(title.upper()), self.styles["point_detail_title"]),
                Spacer(1, 1 * mm),
                Paragraph(xml_text(str(text)), body_style),
            ])
        return content

    def _intro_panel(self, width: float) -> Table:
        icon_width = 9 * mm
        intro = Table([[
            ProfileIcon(self.intro_icon or "speech", 6 * mm, self.palette["gold"]),
            Paragraph(xml_text(self.intro_text or ""), self.styles["point_intro_compact"] if self.compact else self.styles["point_intro"]),
        ]], colWidths=[icon_width, width - icon_width])
        padding = 2.2 * mm if self.compact else 3.2 * mm
        intro.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), translucent_color(self.palette["panel_surface"], 0.52)),
            ("LINEBEFORE", (0, 0), (0, -1), 1.1, color(self.palette["gold"])),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), padding),
            ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding),
            ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ]))
        return intro

    def _intro_and_summary(self) -> Table | list[Any]:
        summary = self._summary()
        if not self.intro_text:
            return summary
        gap = 6 * mm
        summary_width = (self.panel_width - gap) * 0.57
        intro_width = self.panel_width - gap - summary_width
        row = Table(
            [[summary, "", self._intro_panel(intro_width)]],
            colWidths=[summary_width, gap, intro_width],
            hAlign="CENTER",
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return row

    def build(self) -> list[Any]:
        spacing = 3.2 * mm if self.compact else 4.5 * mm
        intro_and_summary = self._intro_and_summary()
        story = intro_and_summary if isinstance(intro_and_summary, list) else [intro_and_summary]
        story.extend([Spacer(1, spacing), self._sign_panel(), *self._interpretations()])
        return story
