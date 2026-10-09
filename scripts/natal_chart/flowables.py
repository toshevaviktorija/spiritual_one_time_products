"""Reusable ReportLab flowables."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from reportlab.pdfbase import pdfmetrics
from reportlab.lib import colors
from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing
from reportlab.platypus import Flowable, Table, TableStyle

from .constants import SIGN_COLORS, SIGN_NAMES


def color(value: str):
    return colors.HexColor(value)


def translucent_color(value: str, opacity: float):
    base = colors.HexColor(value)
    return colors.Color(base.red, base.green, base.blue, alpha=opacity)


def panel_box_style(palette):
    """Shared rounded gold frame and translucent fill for report text boxes."""
    return [
        ("BACKGROUND", (0, 0), (-1, -1), translucent_color(palette["panel_surface"], 0.52)),
        ("BORDERGRADIENT", palette["border_gradient_colors"], palette["border_gradient_locations"]),
        ("ROUNDEDCORNERS", [5, 5, 5, 5]),
    ]


class PanelTable(Table):
    """A text box with a thin rounded border shaded by a multi-stop gradient."""

    def setStyle(self, style):
        commands = style.getCommands() if isinstance(style, TableStyle) else style
        regular = []
        for command in commands:
            if command[0] == "BORDERGRADIENT":
                self.border_gradient = command[1:]
            elif command[0] == "CORNERARTWORK":
                self.corner_artwork = command[1:]
            elif command[0] == "EXTRACORNERARTWORK":
                self.extra_corner_artwork = command[1:]
            elif command[0] == "GRADIENTROWS":
                self.gradient_rows = True
            elif command[0] == "BORDERWIDTH":
                self.border_width = command[1]
            else:
                regular.append(command)
        super().setStyle(TableStyle(regular))

    def draw(self):
        super().draw()
        if not hasattr(self, "border_gradient"):
            return
        canvas = self.canv
        path = canvas.beginPath()

        def rounded_rect(x, y, width, height, radius):
            k = 0.55228475 * radius
            path.moveTo(x + radius, y)
            path.lineTo(x + width - radius, y)
            path.curveTo(x + width - radius + k, y, x + width, y + radius - k, x + width, y + radius)
            path.lineTo(x + width, y + height - radius)
            path.curveTo(x + width, y + height - radius + k, x + width - radius + k, y + height, x + width - radius, y + height)
            path.lineTo(x + radius, y + height)
            path.curveTo(x + radius - k, y + height, x, y + height - radius + k, x, y + height - radius)
            path.lineTo(x, y + radius)
            path.curveTo(x, y + radius - k, x + radius - k, y, x + radius, y)
            path.close()

        rounded_rect(0, 0, self._width, self._height, 5)
        border_width = getattr(self, "border_width", 0.5)
        rounded_rect(border_width, border_width, self._width - 2 * border_width,
                     self._height - 2 * border_width, 5 - border_width)
        shades, locations = self.border_gradient
        canvas.saveState()
        canvas.clipPath(path, stroke=0, fill=0, fillMode=0)
        canvas.linearGradient(0, self._height, self._width, 0,
                              [color(shade) for shade in shades], positions=locations)
        canvas.restoreState()
        if getattr(self, "gradient_rows", False):
            for index, y in enumerate(self._rowpositions[1:-1]):
                thickness = 1.3 if index == 0 else 0.85
                canvas.saveState()
                clip = canvas.beginPath()
                clip.rect(0.5, y - thickness / 2, self._width - 1, thickness)
                canvas.clipPath(clip, stroke=0, fill=0)
                canvas.linearGradient(0, y, self._width, y,
                                      [color(shade) for shade in shades], positions=locations)
                canvas.restoreState()
        for ornament in (getattr(self, "corner_artwork", None), getattr(self, "extra_corner_artwork", None)):
            if ornament is None:
                continue
            image, size, *placement = ornament
            width, height = image.getSize()
            scale = size * 1.2 / max(width, height)
            width, height = width * scale, height * scale
            position = placement[0] if placement else "top_right"
            y = 0.5 if position.startswith("bottom") else self._height - height - 0.5
            x = 0.5 if position.endswith("left") else self._width - width - 0.5
            canvas.drawImage(image, x, y,
                             width=width, height=height, mask="auto")


class ZodiacWheel(Flowable):
    def __init__(self, placements: Sequence[Mapping[str, Any]], size: float, theme: Mapping[str, Any]):
        super().__init__()
        self.width = self.height = size
        self.placements = placements
        self.theme = theme

    def draw(self) -> None:
        canvas = self.canv
        centre = self.width / 2
        outer, inner = self.width * 0.46, self.width * 0.31
        palette = self.theme["colors"]
        canvas.setStrokeColor(color(palette["gold"]))
        canvas.setLineWidth(1.5)
        canvas.circle(centre, centre, outer)
        canvas.circle(centre, centre, inner)
        for index, sign in enumerate(SIGN_NAMES.values()):
            angle = math.radians(90 - index * 30)
            canvas.setStrokeColor(color(palette["gold_light"]))
            canvas.line(centre + inner * math.cos(angle), centre + inner * math.sin(angle), centre + outer * math.cos(angle), centre + outer * math.sin(angle))
            middle = math.radians(75 - index * 30)
            x, y = centre + outer * 0.86 * math.cos(middle), centre + outer * 0.86 * math.sin(middle)
            sign_style = self.theme["design_system"]["text_styles"]["wheel_sign"]
            canvas.setFillColor(color(palette.get(sign_style["color"], sign_style["color"])))
            canvas.setFont(sign_style["font"], sign_style["size"])
            canvas.drawCentredString(x, y - 2, sign[:3].upper())
        for index, point in enumerate(self.placements):
            longitude = point.get("abs_pos", point.get("absolute_longitude"))
            if longitude is None:
                continue
            angle = math.radians(90 - float(longitude))
            radius = inner * (0.82 - (index % 4) * 0.075)
            x, y = centre + radius * math.cos(angle), centre + radius * math.sin(angle)
            planet_style = self.theme["design_system"]["text_styles"]["wheel_planet"]
            canvas.setFillColor(color(palette.get(planet_style["color"], planet_style["color"])))
            canvas.circle(x, y, 2.1, stroke=0, fill=1)
            canvas.setFont(planet_style["font"], planet_style["size"])
            canvas.drawCentredString(x, y + 4, str(point.get("name", ""))[:4].upper())
        centre_style = self.theme["design_system"]["text_styles"]["wheel_center"]
        canvas.setFillColor(color(palette.get(centre_style["color"], centre_style["color"])))
        canvas.setFont(centre_style["font"], centre_style["size"])
        canvas.drawCentredString(centre, centre - 4, "NATAL")


class SparkleBullet(Flowable):
    """A small vector sparkle that does not depend on font glyph support."""

    def __init__(self, size: float, fill_color: str):
        super().__init__()
        self.width = self.height = size
        self.size = size
        self.fill_color = fill_color

    def draw(self) -> None:
        centre = self.size / 2
        radius = self.size / 2
        shoulder = self.size * 0.13
        path = self.canv.beginPath()
        path.moveTo(centre, centre + radius)
        path.lineTo(centre + shoulder, centre + shoulder)
        path.lineTo(centre + radius, centre)
        path.lineTo(centre + shoulder, centre - shoulder)
        path.lineTo(centre, centre - radius)
        path.lineTo(centre - shoulder, centre - shoulder)
        path.lineTo(centre - radius, centre)
        path.lineTo(centre - shoulder, centre + shoulder)
        path.close()
        self.canv.setFillColor(color(self.fill_color))
        self.canv.drawPath(path, stroke=0, fill=1)


class ProfileIcon(Flowable):
    """Small vector icon used by the profile callout panels."""

    def __init__(self, kind: str, size: float, stroke_color: str):
        super().__init__()
        self.kind = kind
        self.width = self.height = size
        self.size = size
        self.stroke_color = stroke_color

    def draw(self) -> None:
        canvas = self.canv
        size = self.size
        canvas.saveState()
        canvas.setStrokeColor(color(self.stroke_color))
        canvas.setFillColor(color(self.stroke_color))
        canvas.setLineWidth(max(1, size * 0.08))
        if self.kind == "target":
            for radius in (0.42, 0.27, 0.10):
                canvas.circle(size / 2, size / 2, size * radius, stroke=1, fill=0)
        elif self.kind == "star":
            SparkleBullet(size, self.stroke_color).drawOn(canvas, 0, 0)
        elif self.kind == "house":
            path = canvas.beginPath()
            path.moveTo(size * 0.08, size * 0.55)
            path.lineTo(size * 0.5, size * 0.92)
            path.lineTo(size * 0.92, size * 0.55)
            path.moveTo(size * 0.2, size * 0.58)
            path.lineTo(size * 0.2, size * 0.1)
            path.lineTo(size * 0.8, size * 0.1)
            path.lineTo(size * 0.8, size * 0.58)
            path.moveTo(size * 0.43, size * 0.1)
            path.lineTo(size * 0.43, size * 0.38)
            path.lineTo(size * 0.58, size * 0.38)
            path.lineTo(size * 0.58, size * 0.1)
            canvas.drawPath(path, stroke=1, fill=0)
        elif self.kind == "person":
            canvas.circle(size * 0.5, size * 0.73, size * 0.15, stroke=0, fill=1)
            path = canvas.beginPath()
            path.moveTo(size * 0.16, size * 0.1)
            path.curveTo(size * 0.2, size * 0.5, size * 0.8, size * 0.5, size * 0.84, size * 0.1)
            canvas.drawPath(path, stroke=1, fill=0)
        elif self.kind == "speech":
            canvas.roundRect(size * 0.08, size * 0.3, size * 0.84, size * 0.55, size * 0.12, stroke=1, fill=0)
            path = canvas.beginPath()
            path.moveTo(size * 0.3, size * 0.3)
            path.lineTo(size * 0.2, size * 0.08)
            path.lineTo(size * 0.48, size * 0.3)
            canvas.drawPath(path, stroke=1, fill=0)
        elif self.kind == "heart":
            path = canvas.beginPath()
            path.moveTo(size * 0.5, size * 0.12)
            path.curveTo(size * 0.12, size * 0.38, size * 0.05, size * 0.72, size * 0.28, size * 0.84)
            path.curveTo(size * 0.42, size * 0.92, size * 0.5, size * 0.8, size * 0.5, size * 0.72)
            path.curveTo(size * 0.5, size * 0.8, size * 0.58, size * 0.92, size * 0.72, size * 0.84)
            path.curveTo(size * 0.95, size * 0.72, size * 0.88, size * 0.38, size * 0.5, size * 0.12)
            canvas.drawPath(path, stroke=1, fill=0)
        elif self.kind == "dumbbell":
            canvas.line(size * 0.24, size * 0.5, size * 0.76, size * 0.5)
            for x in (size * 0.14, size * 0.74):
                canvas.rect(x, size * 0.28, size * 0.12, size * 0.44, stroke=1, fill=0)
            for x in (size * 0.04, size * 0.84):
                canvas.rect(x, size * 0.36, size * 0.1, size * 0.28, stroke=1, fill=0)
        elif self.kind == "briefcase":
            canvas.roundRect(size * 0.08, size * 0.18, size * 0.84, size * 0.58, size * 0.06, stroke=1, fill=0)
            canvas.roundRect(size * 0.34, size * 0.72, size * 0.32, size * 0.16, size * 0.04, stroke=1, fill=0)
            canvas.line(size * 0.08, size * 0.48, size * 0.92, size * 0.48)
            canvas.rect(size * 0.44, size * 0.42, size * 0.12, size * 0.12, stroke=1, fill=0)
        elif self.kind == "graduation":
            path = canvas.beginPath()
            path.moveTo(size * 0.06, size * 0.62)
            path.lineTo(size * 0.5, size * 0.86)
            path.lineTo(size * 0.94, size * 0.62)
            path.lineTo(size * 0.5, size * 0.38)
            path.close()
            canvas.drawPath(path, stroke=1, fill=0)
            canvas.line(size * 0.22, size * 0.53, size * 0.22, size * 0.25)
            band = canvas.beginPath()
            band.moveTo(size * 0.24, size * 0.53)
            band.curveTo(size * 0.3, size * 0.34, size * 0.7, size * 0.34, size * 0.78, size * 0.53)
            canvas.drawPath(band, stroke=1, fill=0)
            canvas.line(size * 0.85, size * 0.66, size * 0.85, size * 0.2)
            canvas.circle(size * 0.85, size * 0.14, size * 0.05, stroke=0, fill=1)
        elif self.kind == "star8":
            centre = size * 0.5
            outer = size * 0.46
            inner = size * 0.18
            path = canvas.beginPath()
            for index in range(16):
                angle = math.radians(90 - index * 22.5)
                radius = outer if index % 2 == 0 else inner
                x = centre + radius * math.cos(angle)
                y = centre + radius * math.sin(angle)
                if index == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.close()
            canvas.drawPath(path, stroke=0, fill=1)
        elif self.kind == "lightning":
            path = canvas.beginPath()
            path.moveTo(size * 0.56, size * 0.96)
            path.lineTo(size * 0.18, size * 0.46)
            path.lineTo(size * 0.46, size * 0.46)
            path.lineTo(size * 0.34, size * 0.04)
            path.lineTo(size * 0.84, size * 0.6)
            path.lineTo(size * 0.56, size * 0.6)
            path.close()
            canvas.drawPath(path, stroke=0, fill=1)
        elif self.kind == "sprig":
            stem = canvas.beginPath()
            stem.moveTo(size * 0.18, size * 0.08)
            stem.curveTo(size * 0.34, size * 0.36, size * 0.56, size * 0.58, size * 0.84, size * 0.9)
            canvas.drawPath(stem, stroke=1, fill=0)
            for x, y, direction in ((0.36, 0.36, -1), (0.52, 0.54, 1), (0.68, 0.71, -1)):
                leaf = canvas.beginPath()
                leaf.moveTo(size * x, size * y)
                leaf.curveTo(size * (x + 0.16 * direction), size * (y + 0.02), size * (x + 0.18 * direction), size * (y + 0.17), size * x, size * (y + 0.16))
                leaf.curveTo(size * (x - 0.03 * direction), size * (y + 0.1), size * (x - 0.03 * direction), size * (y + 0.04), size * x, size * y)
                canvas.drawPath(leaf, stroke=1, fill=0)
        elif self.kind == "rings":
            canvas.circle(size * 0.38, size * 0.5, size * 0.27, stroke=1, fill=0)
            canvas.circle(size * 0.62, size * 0.5, size * 0.27, stroke=1, fill=0)
        elif self.kind == "wave_star":
            wave = canvas.beginPath()
            wave.moveTo(size * 0.04, size * 0.3)
            wave.curveTo(size * 0.2, size * 0.48, size * 0.34, size * 0.12, size * 0.5, size * 0.3)
            wave.curveTo(size * 0.66, size * 0.48, size * 0.8, size * 0.12, size * 0.96, size * 0.3)
            canvas.drawPath(wave, stroke=1, fill=0)
            SparkleBullet(size * 0.48, self.stroke_color).drawOn(canvas, size * 0.28, size * 0.5)
        elif self.kind == "butterfly":
            canvas.line(size * 0.5, size * 0.25, size * 0.5, size * 0.72)
            canvas.circle(size * 0.5, size * 0.78, size * 0.06, stroke=0, fill=1)
            left = canvas.beginPath()
            left.moveTo(size * 0.47, size * 0.55)
            left.curveTo(size * 0.12, size * 0.94, size * 0.04, size * 0.48, size * 0.42, size * 0.38)
            left.curveTo(size * 0.12, size * 0.16, size * 0.22, size * 0.02, size * 0.48, size * 0.3)
            right = canvas.beginPath()
            right.moveTo(size * 0.53, size * 0.55)
            right.curveTo(size * 0.88, size * 0.94, size * 0.96, size * 0.48, size * 0.58, size * 0.38)
            right.curveTo(size * 0.88, size * 0.16, size * 0.78, size * 0.02, size * 0.52, size * 0.3)
            canvas.drawPath(left, stroke=1, fill=0)
            canvas.drawPath(right, stroke=1, fill=0)
        canvas.restoreState()


class ZodiacSignBadge(Flowable):
    """Colored zodiac medallion with a high-contrast white sign glyph."""

    def __init__(self, sign_key: str, symbol: str, symbol_font: str, size: float):
        super().__init__()
        self.sign_key = sign_key
        self.symbol = symbol.replace("\ufe0f", "")
        self.symbol_font = symbol_font
        self.width = self.height = size
        self.size = size

    def draw(self) -> None:
        canvas = self.canv
        centre = self.size / 2
        canvas.saveState()
        canvas.setFillColor(color(SIGN_COLORS.get(self.sign_key, "#744F72")))
        canvas.setStrokeColor(colors.Color(1, 1, 1, alpha=0.72))
        canvas.setLineWidth(max(0.8, self.size * 0.045))
        canvas.circle(centre, centre, self.size * 0.44, stroke=1, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont(self.symbol_font, self.size * 0.52)
        canvas.drawCentredString(centre, centre - self.size * 0.18, self.symbol)
        canvas.restoreState()


class VectorDrawing(Flowable):
    """Scale and center a ReportLab vector drawing inside the story."""

    def __init__(self, drawing: Drawing, width: float, height: float):
        super().__init__()
        self.drawing = drawing
        self.width = width
        self.height = height

    def draw(self) -> None:
        scale = min(self.width / self.drawing.width, self.height / self.drawing.height)
        rendered_width = self.drawing.width * scale
        x_offset = (self.width - rendered_width) / 2
        self.canv.saveState()
        self.canv.translate(x_offset, 0)
        self.canv.scale(scale, scale)
        renderPDF.draw(self.drawing, self.canv, 0, 0)
        self.canv.restoreState()


class FramedWheel(Flowable):
    """Center a vector wheel within a transparent ornamental frame."""

    def __init__(self, drawing: Drawing, image, size: float, wheel_size: float):
        super().__init__()
        self.drawing, self.image = drawing, image
        self.width = self.height = size
        self.wheel_size = wheel_size
        self.hAlign = "CENTER"

    def draw(self) -> None:
        image_width, image_height = self.image.getSize()
        scale = min(self.width / image_width, self.height / image_height)
        frame_width, frame_height = image_width * scale, image_height * scale
        self.canv.drawImage(self.image, (self.width - frame_width) / 2,
                           (self.height - frame_height) / 2,
                           width=frame_width, height=frame_height, mask="auto")
        wheel_scale = min(self.wheel_size / self.drawing.width,
                          self.wheel_size / self.drawing.height)
        self.canv.saveState()
        self.canv.translate((self.width - self.drawing.width * wheel_scale) / 2,
                            (self.height - self.drawing.height * wheel_scale) / 2)
        self.canv.scale(wheel_scale, wheel_scale)
        renderPDF.draw(self.drawing, self.canv, 0, 0)
        self.canv.restoreState()


class RasterArtwork(Flowable):
    """Fit transparent artwork into a centered band without distortion."""

    def __init__(self, image, width: float, height: float):
        super().__init__()
        self.image, self.width, self.height = image, width, height
        self.hAlign = "CENTER"

    def draw(self) -> None:
        width, height = self.image.getSize()
        scale = min(self.width / width, self.height / height)
        width, height = width * scale, height * scale
        self.canv.drawImage(self.image, (self.width - width) / 2,
                           (self.height - height) / 2, width=width, height=height, mask="auto")


class PercentageBar(Flowable):
    """A compact left-to-right balance bar with a translucent remainder."""

    def __init__(self, percentage: float, width: float, height: float, fill_color: str, remainder_color: str):
        super().__init__()
        self.percentage = max(0.0, min(100.0, float(percentage)))
        self.width = width
        self.height = height
        self.fill_color = fill_color
        self.remainder_color = remainder_color

    def draw(self) -> None:
        radius = self.height / 2
        filled_width = self.width * self.percentage / 100
        self.canv.saveState()
        self.canv.setFillColor(translucent_color(self.remainder_color, 0.32))
        self.canv.roundRect(0, 0, self.width, self.height, radius, stroke=0, fill=1)
        if filled_width > 0:
            self.canv.setFillColor(color(self.fill_color))
            self.canv.roundRect(0, 0, max(filled_width, self.height), self.height, radius, stroke=0, fill=1)
        self.canv.restoreState()


class PatternKeywords(Flowable):
    """Center three equally sized rounded keyword badges in a full-width row."""

    def __init__(self, keywords, width, style, fill, border):
        super().__init__()
        self.keywords, self.width, self.style = keywords, width, style
        self.fill, self.border = fill, border
        self.height = 24
        self.gap = 10
        self.badge_width = max(82, max(pdfmetrics.stringWidth(word, style.fontName, style.fontSize) for word in keywords) + 22)
        if len(keywords) * self.badge_width + (len(keywords) - 1) * self.gap > width:
            raise ValueError("Pattern keyword badges exceed the available page width")

    def draw(self):
        canvas = self.canv
        canvas.saveState()
        total = len(self.keywords) * self.badge_width + (len(self.keywords) - 1) * self.gap
        x = (self.width - total) / 2
        canvas.setFont(self.style.fontName, self.style.fontSize)
        for word in self.keywords:
            canvas.setFillColor(color(self.fill))
            canvas.setStrokeColor(color(self.border))
            canvas.setLineWidth(0.8)
            canvas.roundRect(x, 0, self.badge_width, self.height, self.height / 2, stroke=1, fill=1)
            canvas.setFillColor(self.style.textColor)
            ascent, descent = pdfmetrics.getAscentDescent(self.style.fontName, self.style.fontSize)
            canvas.drawCentredString(x + self.badge_width / 2, (self.height - ascent - descent) / 2, word)
            x += self.badge_width + self.gap
        canvas.restoreState()


class OrnamentColumns(Table):
    """A table with PNG dividers drawn at its column boundaries."""

    def __init__(self, *args, separator_image, **kwargs):
        super().__init__(*args, **kwargs)
        self.separator_image = separator_image

    def draw(self):
        super().draw()
        image_width, image_height = self.separator_image.getSize()
        width = min(6, self._height * image_width / image_height)
        for x in self._colpositions[1:-1]:
            self.canv.drawImage(self.separator_image, x - width / 2, 0,
                               width=width, height=self._height, mask="auto")
