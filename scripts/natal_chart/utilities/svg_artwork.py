"""Load SVG artwork while applying a theme-controlled colour."""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from xml.etree import ElementTree

from svglib.svglib import svg2rlg


_PAINTABLE_TAGS = {"circle", "ellipse", "line", "path", "polygon", "polyline", "rect"}


def _themed_style(style: str, colour: str) -> str:
    declarations = [item.strip() for item in style.split(";") if item.strip()]
    declarations = [item for item in declarations if not re.match(r"^(fill|stroke)\s*:", item, re.I)]
    declarations.extend((f"fill:{colour}", f"stroke:{colour}"))
    return ";".join(declarations)


def load_coloured_svg(path: Path, colour: str):
    """Return an svglib drawing with visible fills and strokes recoloured."""
    root = ElementTree.parse(path).getroot()
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag not in _PAINTABLE_TAGS:
            continue
        element.set("style", _themed_style(element.get("style", ""), colour))
        element.attrib.pop("class", None)

    with tempfile.NamedTemporaryFile(suffix=".svg") as temporary:
        ElementTree.ElementTree(root).write(temporary.name, encoding="utf-8", xml_declaration=True)
        return svg2rlg(temporary.name)
