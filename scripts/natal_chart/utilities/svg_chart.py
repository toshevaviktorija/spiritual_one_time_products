"""Prepare a Kerykeion SVG wheel for themed vector PDF rendering."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from lxml import etree
from reportlab.graphics.shapes import Drawing
from svglib.svglib import svg2rlg

KERYKEION_NAMESPACE = "https://www.kerykeion.net/"
VARIABLE_PATTERN = re.compile(r"(--[\w-]+)\s*:\s*([^;]+);")


@dataclass(frozen=True)
class PreparedChart:
    drawing: Drawing
    metadata: tuple[str, ...]


def _node(root: etree._Element, name: str) -> etree._Element | None:
    matches = root.xpath(f"//*[@kr:node='{name}']", namespaces={"kr": KERYKEION_NAMESPACE})
    return matches[0] if matches else None


def _metadata(root: etree._Element) -> tuple[str, ...]:
    values = [" ".join(text.itertext()).strip() for text in root.xpath("//*[local-name()='text']")]

    def first(prefix: str) -> str | None:
        return next((value for value in values if value.startswith(prefix)), None)

    chart_type = first("Type:")
    houses = next((value for value in values if value.endswith(" Houses")), None)
    zodiac = first("Zodiac:")
    lunar_day = first("Lunar phase day:")
    lunar_phase = first("Lunar phase:")
    perspective = next((value for value in values if "Geocentric" in value), None)
    formatted = [
        chart_type.removeprefix("Type:").strip() if chart_type else None,
        houses,
        f"{zodiac.removeprefix('Zodiac:').strip()} Zodiac" if zodiac else None,
        f"Lunar Day {lunar_day.removeprefix('Lunar phase day:').strip()}" if lunar_day else None,
        lunar_phase.removeprefix("Lunar phase:").strip() if lunar_phase else None,
        perspective,
    ]
    return tuple(value for value in formatted if value)


def _isolate_wheel(root: etree._Element) -> None:
    main_text = _node(root, "Main_Text")
    lunar_phase = _node(root, "Lunar_Phase")
    for removable in (main_text, lunar_phase):
        if removable is not None and removable.getparent() is not None:
            removable.getparent().remove(removable)

    main_content = _node(root, "Main_Content")
    full_wheel = _node(root, "Full_Wheel")
    if main_content is None or full_wheel is None:
        raise ValueError("The SVG does not contain a Kerykeion Full_Wheel group")
    for child in list(main_content):
        if child is not full_wheel:
            main_content.remove(child)

    root.set("viewBox", "50 40 500 500")
    root.set("width", "500")
    root.set("height", "500")
    root.attrib.pop("style", None)


def _resolve_theme_variables(svg_text: str, palette: Mapping[str, str]) -> str:
    variables = dict(VARIABLE_PATTERN.findall(svg_text))
    variables.update({
        "--kerykeion-color-black": palette["primary"],
        "--kerykeion-color-white": palette["page_background"],
        "--kerykeion-color-neutral-content": palette["text"],
        "--kerykeion-color-base-content": palette["primary"],
        "--kerykeion-color-primary": palette["secondary"],
        "--kerykeion-color-secondary": palette["primary"],
        "--kerykeion-color-accent": palette["gold"],
        "--kerykeion-color-neutral": palette["primary"],
        "--kerykeion-color-base-100": palette["page_background"],
        "--kerykeion-color-success": palette["secondary"],
        "--kerykeion-color-warning": palette["gold"],
        "--kerykeion-color-error": "#A95F78",
        "--kerykeion-color-base-200": palette["box_background"],
        "--kerykeion-color-base-300": palette["alternate_row"],
    })

    def resolve(name: str, seen: set[str] | None = None) -> str:
        seen = set() if seen is None else seen
        if name in seen:
            return palette["text"]
        value = variables.get(name, palette["text"]).strip()
        match = re.fullmatch(r"var\((--[\w-]+)\)", value)
        return resolve(match.group(1), seen | {name}) if match else value

    return re.sub(r"var\((--[\w-]+)\)", lambda match: resolve(match.group(1)), svg_text)


def prepare_chart(svg_path: Path, palette: Mapping[str, str]) -> PreparedChart:
    parser = etree.XMLParser(remove_blank_text=False, recover=True)
    root = etree.parse(str(svg_path), parser).getroot()
    metadata = _metadata(root)
    _isolate_wheel(root)
    svg_text = etree.tostring(root, encoding="unicode")
    themed_svg = _resolve_theme_variables(svg_text, palette)
    drawing = svg2rlg(io.BytesIO(themed_svg.encode("utf-8")))
    if drawing is None:
        raise ValueError(f"Unable to render chart SVG: {svg_path}")
    return PreparedChart(drawing=drawing, metadata=metadata)
