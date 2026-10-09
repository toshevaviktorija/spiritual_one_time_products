"""Page templates and top-level PDF assembly."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import BaseDocTemplate, Frame, HRFlowable, KeepTogether, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle

from .constants import PLANET_SYMBOLS, SIGN_NAMES
from .flowables import PanelTable, panel_box_style, FramedWheel, OrnamentColumns, PatternKeywords, RasterArtwork, PercentageBar, ProfileIcon, SparkleBullet, VectorDrawing, color, translucent_color
from .aspects import AspectSection
from .house import HousePattern
from .models import NatalChartData
from .point import PointPattern
from .utilities.formatting import xml_text
from .utilities.page_heading import page_heading
from .utilities.svg_chart import prepare_chart
from .utilities.svg_artwork import load_coloured_svg
from .utilities.theme import resolve_artwork


class NumberedCanvas(Canvas):
    """Defer page output until the final page count is known."""

    def __init__(self, *args, footer_style: ParagraphStyle, **kwargs):
        super().__init__(*args, **kwargs)
        self.footer_style = footer_style
        self.page_states: list[dict[str, Any]] = []

    def showPage(self) -> None:
        self.page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self.page_states)
        for state in self.page_states:
            self.__dict__.update(state)
            self.saveState()
            self.setFillColor(self.footer_style.textColor)
            self.setFont(self.footer_style.fontName, self.footer_style.fontSize)
            self.drawCentredString(self._pagesize[0] / 2, 8.5 * mm,
                                   f"Page {self._pageNumber} out of {total}")
            self.restoreState()
            super().showPage()
        super().save()


class NatalChartDocument:
    def __init__(self, data: NatalChartData, theme: Mapping[str, Any], output: Path):
        self.data, self.theme, self.output = data, theme, output
        self.palette, self.layout = theme["colors"], theme["layout"]
        self.page_size = A4 if theme["document"].get("page_size", "A4").upper() == "A4" else LETTER
        self.body_frame_inset = 17 * mm
        self.body_frame_padding = 6  # ReportLab Frame's default padding, in points.
        # Match normal paragraphs exactly: frame width minus its left/right padding.
        self.panel_width = self.page_size[0] - 2 * self.body_frame_inset - 2 * self.body_frame_padding
        self.symbol_font = self._register_symbol_font()
        self.theme_fonts = self._register_theme_fonts()
        artwork_presets = theme["design_system"]["artwork"]
        self.palette["panel_border"] = artwork_presets["frame"]["color"]
        separator_preset = artwork_presets[theme["design_system"]["active_separator"]]
        separator_path = resolve_artwork(dict(theme), separator_preset.get("file"))
        frame_preset = artwork_presets["frame"]
        self.separator_image = self._tinted_png(separator_path, frame_preset["color"]) if separator_path else None
        frame_path = resolve_artwork(dict(theme), frame_preset.get("file"))
        self.frame_drawing = None
        self.frame_image = None
        if frame_path and frame_path.suffix.lower() == ".png":
            self.frame_image = self._tinted_png(frame_path, frame_preset["color"])
        elif frame_path:
            self.frame_drawing = load_coloured_svg(frame_path, frame_preset["color"])
        self.styles = self._make_styles()
        self.palette["corner_artwork"] = self._tinted_png(
            resolve_artwork(dict(theme), "assets/ornate_corner.png"),
            frame_preset["color"], crop=True, mirror=True)
        self.palette["corner_artwork_bottom_right"] = self._tinted_png(
            resolve_artwork(dict(theme), "assets/ornate_corner.png"),
            frame_preset["color"], crop=True, mirror=True, flip_vertical=True)
        self.palette["corner_artwork_bottom_left"] = self._tinted_png(
            resolve_artwork(dict(theme), "assets/ornate_corner.png"),
            frame_preset["color"], crop=True, flip_vertical=True)
        self.pattern_branch = self._tinted_png(resolve_artwork(dict(theme), "assets/branch.png"), frame_preset["color"], crop=True)
        self.pattern_branch_left = self._tinted_png(resolve_artwork(dict(theme), "assets/branch.png"), frame_preset["color"], crop=True, mirror=True)
        self.vertical_separator = self._tinted_png(resolve_artwork(dict(theme), "assets/vertical_separator.png"), frame_preset["color"], crop=True)

    @staticmethod
    def _tinted_png(path: Path, colour: str, *, crop: bool = False, mirror: bool = False, flip_vertical: bool = False) -> ImageReader:
        """Apply the ornament colour through the PNG's original alpha mask."""
        with Image.open(path) as source:
            rgba = source.convert("RGBA")
            tinted = Image.new("RGBA", rgba.size, colour)
            tinted.putalpha(rgba.getchannel("A"))
            if crop and tinted.getbbox():
                tinted = tinted.crop(tinted.getbbox())
            if mirror:
                tinted = tinted.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            if flip_vertical:
                tinted = tinted.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        return ImageReader(tinted)

    def _ornate_separator(self, width: float, height: float) -> Any:
        if self.separator_image is not None:
            return RasterArtwork(self.separator_image, width, height)
        return HRFlowable(width=width, thickness=0.55,
                          color=color(self.theme["design_system"]["artwork"]["frame"]["color"]), hAlign="CENTER")

    @staticmethod
    def _register_symbol_font() -> str:
        font_name = "VenastellaSymbols"
        if font_name in pdfmetrics.getRegisteredFontNames():
            return font_name
        candidates = (
            Path("/System/Library/Fonts/Apple Symbols.ttf"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
        )
        for path in candidates:
            if path.exists():
                pdfmetrics.registerFont(TTFont(font_name, str(path)))
                return font_name
        return "Helvetica"

    def _register_theme_fonts(self) -> dict[str, str]:
        """Register optional branded fonts and retain deliberate fallbacks."""
        registered: dict[str, str] = {}
        for key, preset in self.theme["design_system"].get("fonts", {}).items():
            font_name = str(preset["name"])
            font_path = resolve_artwork(dict(self.theme), preset.get("file"))
            if font_path and font_name not in pdfmetrics.getRegisteredFontNames():
                try:
                    pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
                except Exception:
                    font_name = str(preset["fallback"])
            elif not font_path:
                font_name = str(preset["fallback"])
            registered[key] = font_name
        return registered

    def _make_styles(self) -> dict[str, ParagraphStyle]:
        """Build all ReportLab styles from the editable design-system presets."""
        presets = self.theme["design_system"]["text_styles"]
        base = getSampleStyleSheet()
        alignments = {"left": TA_LEFT, "center": TA_CENTER, "right": TA_RIGHT, "justify": TA_JUSTIFY}
        styles: dict[str, ParagraphStyle] = {}

        def make_style(key: str) -> ParagraphStyle:
            if key in styles:
                return styles[key]
            preset = presets[key]
            inherited = preset.get("extends")
            parent = make_style(inherited) if inherited else base[preset.get("parent", "BodyText")]
            font_token = preset.get("font", parent.fontName)
            if font_token == "$symbol_font":
                font_name = self.symbol_font
            elif isinstance(font_token, str) and font_token.startswith("$"):
                font_name = self.theme_fonts.get(font_token[1:], parent.fontName)
            else:
                font_name = font_token
            colour_role = preset.get("color")
            kwargs: dict[str, Any] = {
                "fontName": font_name,
                "fontSize": preset.get("size", parent.fontSize),
                "leading": preset.get("leading", parent.leading),
                "alignment": alignments.get(preset.get("align", "left"), TA_LEFT),
                "spaceBefore": preset.get("space_before", 0),
                "spaceAfter": preset.get("space_after", 0),
            }
            if colour_role:
                kwargs["textColor"] = color(self.palette.get(colour_role, colour_role))
            styles[key] = ParagraphStyle(key, parent=parent, **kwargs)
            return styles[key]

        for style_key in presets:
            make_style(style_key)
        return styles

    def _draw_image_cover(self, canvas, path: Path, opacity: float) -> None:
        reader = ImageReader(str(path))
        image_width, image_height = reader.getSize()
        page_width, page_height = self.page_size
        scale = max(page_width / image_width, page_height / image_height)
        width, height = image_width * scale, image_height * scale
        canvas.saveState()
        if hasattr(canvas, "setFillAlpha"):
            canvas.setFillAlpha(opacity)
        canvas.drawImage(reader, (page_width - width) / 2, (page_height - height) / 2, width, height, mask="auto")
        canvas.restoreState()

    def _ornaments(self, canvas, inset: float = 10 * mm) -> None:
        if not self.layout.get("show_ornaments", True):
            return
        drawing = self.frame_drawing
        if drawing is None and self.frame_image is None:
            return
        page_width, page_height = self.page_size
        width, height = self.frame_image.getSize() if self.frame_image else (drawing.width, drawing.height)
        scale = min(page_width / width, page_height / height)
        rendered_width = width * scale
        rendered_height = height * scale
        form_name = "VenastellaPageFrame"
        if not canvas.hasForm(form_name):
            canvas.beginForm(form_name, 0, 0, page_width, page_height)
            canvas.saveState()
            canvas.translate((page_width - rendered_width) / 2, (page_height - rendered_height) / 2)
            canvas.scale(scale, scale)
            if self.frame_image:
                canvas.drawImage(self.frame_image, 0, 0, width=width, height=height, mask="auto")
            else:
                renderPDF.draw(drawing, canvas, 0, 0)
            canvas.restoreState()
            canvas.endForm()
        canvas.doForm(form_name)

    def _cover_page(self, canvas, _doc) -> None:
        page_width, page_height = self.page_size
        canvas.saveState()
        canvas.setFillColor(color(self.palette["cover_background"]))
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.restoreState()
        artwork = resolve_artwork(self.theme, self.theme.get("artwork", {}).get("cover_image"))
        if artwork:
            self._draw_image_cover(canvas, artwork, float(self.theme["artwork"].get("cover_opacity", 1)))
        self._ornaments(canvas, 13 * mm)
        canvas.setTitle(f"{self.theme['document']['title']} - {self.data.name}")
        canvas.setAuthor(self.theme["document"].get("author") or "Venastella")

    def _body_page(self, canvas, doc) -> None:
        page_width, page_height = self.page_size
        canvas.saveState()
        canvas.setFillColor(color(self.palette["page_background"]))
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.restoreState()
        artwork = resolve_artwork(self.theme, self.theme.get("artwork", {}).get("background_image"))
        if artwork:
            self._draw_image_cover(canvas, artwork, float(self.theme["artwork"].get("background_opacity", 1)))
        self._ornaments(canvas)

    def _welcome_page(self, canvas, _doc) -> None:
        page_width, page_height = self.page_size
        canvas.saveState()
        canvas.setFillColor(color(self.palette["page_background"]))
        canvas.rect(0, 0, page_width, page_height, stroke=0, fill=1)
        canvas.restoreState()
        artwork = resolve_artwork(self.theme, self.theme.get("artwork", {}).get("background_image"))
        if artwork:
            self._draw_image_cover(canvas, artwork, float(self.theme["artwork"].get("background_opacity", 1)))
        self._ornaments(canvas, 13 * mm)

    def _welcome_story(self) -> list[Any]:
        welcome = self.theme["welcome"]
        bullet_rows = []
        for item in welcome["bullets"]:
            bullet_rows.append([
                SparkleBullet(4.2 * mm, self.palette["gold"]),
                Paragraph(xml_text(item), self.styles["welcome_bullet"]),
            ])
        bullets = Table(bullet_rows, colWidths=[8 * mm, self.page_size[0] - 76 * mm], hAlign="LEFT")
        bullets.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        return [
            *page_heading(welcome["title"], self.styles, self.palette, self.panel_width),
            Paragraph(xml_text(welcome["subtitle"]), self.styles["welcome_subtitle"]),
            Spacer(1, 6 * mm),
            Paragraph(xml_text(welcome["intro"]), self.styles["welcome_body"]),
            Spacer(1, 8 * mm),
            Paragraph(xml_text(welcome["heading"]), self.styles["welcome_heading"]),
            Spacer(1, 3 * mm),
            bullets,
            Spacer(1, 6 * mm),
            Paragraph(xml_text(welcome["closing"]), self.styles["welcome_body"]),
        ]

    def _chart_story(self) -> list[Any]:
        chart_config = self.theme["chart_page"]
        svg_path = resolve_artwork(self.theme, chart_config["svg_file"])
        if svg_path is None:
            raise FileNotFoundError(f"Chart SVG not found: {chart_config['svg_file']}")
        prepared = prepare_chart(svg_path, self.palette)
        metadata = "  ·  ".join(prepared.metadata)
        chart_width = self.page_size[0] - 70 * mm
        chart_size = 120 * mm
        frame_path = resolve_artwork(self.theme, chart_config.get("frame_image"))
        wheel = VectorDrawing(prepared.drawing, chart_width, chart_size)
        if frame_path:
            frame_color = self.theme["design_system"]["artwork"]["frame"]["color"]
            frame_image = self._tinted_png(frame_path, frame_color)
            wheel = FramedWheel(prepared.drawing, frame_image, 150 * mm, chart_size)
        return [
            *page_heading(chart_config["title"], self.styles, self.palette, self.panel_width),
            Paragraph(xml_text(chart_config["description"]), self.styles["chart_description"]),
            Spacer(1, 7 * mm),
            wheel,
            Spacer(1, 4 * mm),
            self._chart_big_three_columns(),
            Spacer(1, 5 * mm),
            Paragraph(xml_text(metadata), self.styles["chart_metadata"]),
        ]

    def _chart_big_three_columns(self) -> Table:
        columns: list[list[Any]] = []
        for key, label, symbol in (("sun", "SUN", "☉"), ("moon", "MOON", "☽"),
                                   ("ascendant", "ASCENDANT", "↑")):
            point = self.data.subject.get(key) or {}
            sign_key = str(point.get("sign") or "")
            sign_name = SIGN_NAMES.get(sign_key, sign_key)
            zodiac = str(point.get("emoji") or "").replace("\ufe0f", "")
            columns.append([
                Paragraph(xml_text(sign_name.upper()), self.styles["chart_sign_name"]),
                Paragraph(xml_text(zodiac), self.styles["chart_sign_symbol"]),
                Paragraph(f"<font name='{self.symbol_font}'>{symbol}</font> &nbsp; {label}",
                          self.styles["chart_point_label"]),
            ])
        table = Table([columns], colWidths=[self.panel_width / 3] * 3, hAlign="CENTER")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LINEAFTER", (0, 0), (1, 0), 0.8,
             color(self.theme["design_system"]["artwork"]["frame"]["color"])),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
        ]))
        return table

    def _big_three_story(self) -> list[Any]:
        planet_symbols = {"sun": "☉", "moon": "☽", "ascendant": "●"}
        content: list[Any] = [
            *page_heading("The Big Three", self.styles, self.palette, self.panel_width),
        ]
        house_names = list(self.data.subject.get("houses_names_list") or [])
        for index, key in enumerate(("sun", "moon", "ascendant")):
            point = self.data.subject.get(key) or {}
            sign_name = str(point.get("sign") or "-")
            sign_name = SIGN_NAMES.get(sign_name, sign_name)
            zodiac_symbol = str(point.get("emoji") or "").replace("\ufe0f", "")
            house_name = point.get("house")
            house_number = house_names.index(house_name) + 1 if house_name in house_names else "-"
            header = f"<b>{xml_text(str(point.get('name') or key).upper())}</b> <font name='{self.symbol_font}'>{planet_symbols[key]}</font> <b>{xml_text(sign_name.upper())}</b>"
            heading = Table([[
                Paragraph(xml_text(zodiac_symbol), self.styles["big_three_symbol"]),
                [Paragraph(header, self.styles["big_three_header"]), Paragraph(f"{float(point.get('position', 0)):.1f}°  ·  House {house_number}", self.styles["big_three_meta"])],
            ]], colWidths=[18 * mm, self.page_size[0] - 70 * mm], hAlign="LEFT")
            heading.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            life_area = str(point.get("life_area") or "").rstrip(".")
            meanings = [point.get("sign_meaning"), point.get("house_meaning")]
            meaning = " ".join(str(value) for value in meanings if value)
            content.extend([
                heading,
                Spacer(1, 4 * mm),
                Paragraph(xml_text(life_area), self.styles["big_three_life"]),
                Spacer(1, 3 * mm),
                Paragraph(xml_text(meaning), self.styles["big_three_body"]),
                Spacer(1, 5 * mm),
            ])
            if index < 2:
                content.extend([self._ornate_separator(self.panel_width, 12 * mm), Spacer(1, 5 * mm)])
        return content

    def _cream_panel(self, content: list[Any], icon: str | None = None, compact: bool = False) -> Table:
        panel_width = self.panel_width
        if icon:
            cells: list[Any] = [
                ProfileIcon(icon, 7 * mm, self.palette["gold"]),
                content,
            ]
            widths = [12 * mm, panel_width - 12 * mm]
        else:
            cells = [content]
            widths = [panel_width]
        table = PanelTable([cells], colWidths=widths, hAlign="CENTER")
        padding = 4 * mm if not compact else 3 * mm
        table.setStyle(TableStyle([
            *panel_box_style(self.palette),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), padding), ("RIGHTPADDING", (0, 0), (-1, -1), padding),
            ("TOPPADDING", (0, 0), (-1, -1), padding), ("BOTTOMPADDING", (0, 0), (-1, -1), padding),
        ]))
        return table

    def _point_pattern(
        self,
        key: str,
        compact: bool = False,
        title: str | None = None,
        intro_text: str | None = None,
        intro_icon: str | None = None,
        life_area: str | None = None,
    ) -> list[Any]:
        return PointPattern(
            key=key,
            point=self.data.subject.get(key) or {},
            styles=self.styles,
            palette=self.palette,
            symbol_font=self.symbol_font,
            house_names=list(self.data.subject.get("houses_names_list") or []),
            panel_width=self.panel_width,
            title_override=title,
            compact=compact,
            intro_text=intro_text,
            intro_icon=intro_icon,
            life_area_override=life_area,
        ).build()

    def _core_identity_story(self) -> list[Any]:
        copy = self.theme["profile_pages"]
        return [
            *page_heading(copy["core_title"], self.styles, self.palette, self.panel_width),
            self._cream_panel([Paragraph(xml_text(copy["core_intro"]), self.styles["callout_box"])]),
            Spacer(1, 9 * mm),
            *self._point_pattern("sun", intro_text=copy["sun_callout"], intro_icon="star"),
        ]

    def _two_point_stack(self, first: list[Any], second: list[Any]) -> Table:
        """Give paired points equal full-page regions with a swappable divider row."""
        stack_height = 226 * mm
        divider_height = 22 * mm
        point_height = (stack_height - divider_height) / 2
        divider = self._paired_separator()
        table = Table(
            [[first], [divider], [second]],
            colWidths=[self.panel_width],
            rowHeights=[point_height, divider_height, point_height],
            hAlign="CENTER",
            splitByRow=0,
        )
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (0, 0), "MIDDLE"),
            ("VALIGN", (0, 1), (0, 1), "MIDDLE"),
            ("VALIGN", (0, 2), (0, 2), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return table

    def _paired_separator(self) -> Any:
        return self._ornate_separator(self.panel_width, 22 * mm)

    def _house_separator(self) -> Any:
        return self._ornate_separator(self.panel_width, 16 * mm)

    def _moon_ascendant_story(self) -> list[Any]:
        copy = self.theme["profile_pages"]
        content: list[Any] = [
            *page_heading(copy["moon_ascendant_title"], self.styles, self.palette, self.panel_width),
            self._two_point_stack(
                self._point_pattern("moon", compact=True, intro_text=copy["moon_callout"], intro_icon="house"),
                self._point_pattern("ascendant", compact=True, intro_text=copy["ascendant_callout"], intro_icon="person"),
            ),
        ]
        return content

    def _midheaven_story(self) -> list[Any]:
        copy = self.theme["profile_pages"]
        return [
            Spacer(1, 7 * mm),
            *self._point_pattern(
                "medium_coeli",
                title="Midhaven",
                intro_text=copy["midheaven_intro"],
                intro_icon="briefcase",
            ),
        ]

    def _personal_planets_mercury_story(self) -> list[Any]:
        copy = self.theme["personal_planets"]
        return [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
            self._cream_panel([Paragraph(xml_text(copy["overview"]), self.styles["callout_box"])]),
            Spacer(1, 9 * mm),
            *self._point_pattern("mercury", intro_text=copy["mercury_intro"], intro_icon="speech"),
        ]

    def _personal_planets_venus_mars_story(self) -> list[Any]:
        copy = self.theme["personal_planets"]
        return [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
            self._two_point_stack(
                self._point_pattern("venus", compact=True, intro_text=copy["venus_intro"], intro_icon="heart"),
                self._point_pattern("mars", compact=True, intro_text=copy["mars_intro"], intro_icon="dumbbell"),
            ),
        ]

    def _social_planets_story(self) -> list[Any]:
        copy = self.theme["social_planets"]
        return [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
            self._two_point_stack(
                self._point_pattern("jupiter", compact=True, intro_text=copy["jupiter_intro"], intro_icon="graduation"),
                self._point_pattern("saturn", compact=True, intro_text=copy["saturn_intro"], intro_icon="briefcase"),
            ),
        ]

    def _generational_points_story(self) -> list[Any]:
        copy = self.theme["generational_points"]
        return [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
            self._two_point_stack(
                self._point_pattern("mean_node", title="North Node", compact=True, intro_text=copy["north_node_intro"], intro_icon="star8"),
                self._point_pattern("mean_lilith", title="Lilith", compact=True, intro_text=copy["lilith_intro"], intro_icon="lightning"),
            ),
        ]

    def _additional_points_story(self, page_key: str, first_key: str, second_key: str) -> list[Any]:
        copy = self.theme["additional_points"]
        page = copy[page_key]
        first = copy[first_key]
        second = copy[second_key]
        return [
            *page_heading(page["title"], self.styles, self.palette, self.panel_width),
            self._two_point_stack(
                self._point_pattern(first_key, title=first.get("title"), compact=True, life_area=first["life_area"], intro_text=first["intro"], intro_icon=first["icon"]),
                self._point_pattern(second_key, title=second.get("title"), compact=True, life_area=second["life_area"], intro_text=second["intro"], intro_icon=second["icon"]),
            ),
        ]

    def _house_pattern(self, number: int) -> list[Any]:
        key = f"{('first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth', 'ninth', 'tenth', 'eleventh', 'twelfth')[number - 1]}_house"
        return HousePattern(
            number=number,
            house=self.data.subject.get(key) or {},
            meaning=self.theme["house_meanings"][key],
            planets=self.data.planets,
            styles=self.styles,
            palette=self.palette,
            symbol_font=self.symbol_font,
            panel_width=self.panel_width,
        ).build()

    def _houses_story(self, first: int, second: int, *, intro: bool = False) -> list[Any]:
        """Lay out two house profiles with one spacious separator."""
        copy = self.theme["house_pages"]
        story: list[Any] = [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
        ]
        if intro:
            story.extend([
                self._cream_panel([Paragraph(xml_text(copy["intro"]), self.styles["callout_box"])]),
                Spacer(1, 5 * mm),
            ])
        # Minimum heights leave breathing room without forcing text into fixed boxes.
        house_height = (94 if intro else 105) * mm
        stack = Table(
            [[self._house_pattern(first)], [self._house_separator()], [self._house_pattern(second)]],
            colWidths=[self.panel_width],
            minRowHeights=[house_height, 16 * mm, house_height],
            splitByRow=0,
        )
        stack.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(stack)
        return story

    def _aggregate_panel(self, content: list[Any], width: float, height: float | None = None) -> Table:
        table = PanelTable([[content]], colWidths=[width], rowHeights=[height], hAlign="CENTER", cornerRadii=[5, 5, 5, 5])
        table.setStyle(TableStyle([
            *panel_box_style(self.palette),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4.5 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 4.5 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 4 * mm),
        ]))
        return table

    def _aggregate_balance_columns(
        self,
        element_content: list[Any],
        modality_content: list[Any],
        full_width: float,
        gap: float,
    ) -> Table:
        """Render equal-size balance panels without nested-table width drift."""
        column_width = (full_width - gap) / 2
        panels = [self._aggregate_panel(content, column_width)
                  for content in (element_content, modality_content)]
        height = max(panel.wrap(column_width, self.page_size[1])[1] for panel in panels)
        panels = [self._aggregate_panel(content, column_width, height)
                  for content in (element_content, modality_content)]
        columns = Table([[panels[0], "", panels[1]]],
                        colWidths=[column_width, gap, column_width], hAlign="CENTER")
        columns.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return columns

    def _balance_rows(self, balance: Mapping[str, Any], keys: tuple[str, ...], colors_by_key: Mapping[str, str], width: float) -> list[Any]:
        rows: list[Any] = []
        for key in keys:
            value = balance.get(key)
            if not isinstance(value, Mapping):
                continue
            percentage = float(value.get("percentage") or 0)
            rows.extend([
                Paragraph(f"{xml_text(key.title())}  <b>{percentage:.0f}%</b>", self.styles["aggregate_label"]),
                Spacer(1, 0.7 * mm),
                PercentageBar(percentage, width, 3.1 * mm, colors_by_key[key], self.palette["gold_light"]),
                Spacer(1, 1.5 * mm),
            ])
        return rows

    def _aggregate_story(self) -> list[Any]:
        aggregates = self.data.premium_aggregates
        if not aggregates:
            return []
        labels = self.theme["aggregate_page"]
        dominant = aggregates.get("dominantPlanet") or {}
        elements = aggregates.get("elementBalance") or {}
        modalities = aggregates.get("modalityBalance") or {}
        hemispheres = aggregates.get("hemisphereBalance") or {}
        full_width = self.panel_width
        column_gap = 5 * mm
        column_width = (full_width - column_gap) / 2
        bar_width = column_width - 9 * mm

        dominant_name = str(dominant.get("name") or "")
        planet_symbol = PLANET_SYMBOLS.get(dominant_name, "●")
        dominant_content: list[Any] = [
            Paragraph(xml_text(labels["dominant_planet_title"]), self.styles["aggregate_title"]),
        ]
        description = xml_text(dominant.get("description") or "")
        if dominant_name:
            heading = (f"<font color='{self.palette['gold_light']}'>"
                       f"<font name='{self.symbol_font}' size='18'>{planet_symbol}</font> "
                       f"<font name='Times-Bold' size='13'>{xml_text(dominant_name)}</font></font>")
            description = f"{heading} &nbsp; {description}"
        if description:
            dominant_content.extend([Spacer(1, 2 * mm),
                                     Paragraph(description, self.styles["dominant_description"])])
        if dominant.get("interpretation"):
            dominant_content.extend([Spacer(1, 2.5 * mm), Paragraph(xml_text(dominant["interpretation"]), self.styles["aggregate_body"])])

        element_content: list[Any] = [Paragraph(xml_text(labels["element_balance_title"]), self.styles["aggregate_title"])]
        if elements.get("description"):
            element_content.extend([Spacer(1, 1 * mm), Paragraph(xml_text(elements["description"]), self.styles["aggregate_description"]), Spacer(1, 2 * mm)])
        element_content.extend(self._balance_rows(elements, ("fire", "earth", "air", "water"), {
            "fire": "#C0526B", "earth": "#70875F", "air": self.palette["gold"], "water": self.palette["primary"],
        }, bar_width))
        if elements.get("interpretation"):
            element_content.append(Paragraph(xml_text(elements["interpretation"]), self.styles["aggregate_body"]))

        modality_content: list[Any] = [Paragraph(xml_text(labels["modality_balance_title"]), self.styles["aggregate_title"])]
        if modalities.get("description"):
            modality_content.extend([Spacer(1, 1 * mm), Paragraph(xml_text(modalities["description"]), self.styles["aggregate_description"]), Spacer(1, 2 * mm)])
        modality_content.extend(self._balance_rows(modalities, ("cardinal", "fixed", "mutable"), {
            "cardinal": self.palette["gold"], "fixed": self.palette["primary"], "mutable": "#70875F",
        }, bar_width))
        if modalities.get("interpretation"):
            modality_content.append(Paragraph(xml_text(modalities["interpretation"]), self.styles["aggregate_body"]))

        hemisphere_content: list[Any] = [Paragraph(xml_text(labels["hemisphere_balance_title"]), self.styles["aggregate_title"])]
        if hemispheres.get("description"):
            hemisphere_content.extend([Spacer(1, 1 * mm), Paragraph(xml_text(hemispheres["description"]), self.styles["aggregate_description"]), Spacer(1, 2 * mm)])
        for comparison_key, left_key, right_key in (("eastWest", "east", "west"), ("northSouth", "north", "south")):
            comparison = hemispheres.get(comparison_key) or {}
            left = comparison.get(left_key) or {}
            right = comparison.get(right_key) or {}
            hemisphere_content.extend([
                Paragraph(f"{left_key.title()} ({int(left.get('count') or 0)})  -  {right_key.title()} ({int(right.get('count') or 0)})", self.styles["aggregate_label"]),
                Spacer(1, 0.7 * mm),
                PercentageBar(float(left.get("percentage") or 0), full_width - 9 * mm, 3.2 * mm, self.palette["primary"], self.palette["gold_light"]),
            ])
            if comparison.get("interpretation"):
                hemisphere_content.extend([Spacer(1, 1 * mm), Paragraph(xml_text(comparison["interpretation"]), self.styles["aggregate_body"])])
            hemisphere_content.append(Spacer(1, 1.8 * mm))

        columns = self._aggregate_balance_columns(element_content, modality_content, full_width, column_gap)
        return [
            *page_heading(labels["title"], self.styles, self.palette, self.panel_width),
            self._corner_panel(self._aggregate_panel(dominant_content, full_width), 22 * mm),
            Spacer(1, 4 * mm),
            columns,
            Spacer(1, 4 * mm),
            self._aggregate_panel(hemisphere_content, full_width),
        ]

    def _pattern_details(self, pattern: Mapping[str, Any]) -> Table:
        interpretation = pattern["interpretation"]
        apex = pattern.get("apex") or {}
        position = " in ".join(str(apex.get(key) or "") for key in ("displayName", "sign") if apex.get(key))
        column_width = self.panel_width / 2
        inner_width = column_width - 6 * mm
        gold = self.theme["design_system"]["artwork"]["frame"]["color"]

        def column(icon: str, title: str, detail: str, suffix: str = "") -> list[Any]:
            heading = xml_text(title)
            if suffix:
                heading += f" <font name='Helvetica'>{xml_text(suffix)}</font>"
            header = Table([[ProfileIcon(icon, 5 * mm, gold), Paragraph(heading, self.styles["pattern_detail_heading"])]],
                           colWidths=[8 * mm, inner_width - 8 * mm])
            header.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))
            return [header, Spacer(1, 3 * mm), Paragraph(xml_text(detail or ""), self.styles["pattern_detail_body"])]

        table = OrnamentColumns([[
            column("target", "Your focal point", interpretation.get("apexFocus"), position),
            column("sprig", "The growth edge", interpretation.get("challenge")),
        ]], colWidths=[column_width, column_width], separator_image=self.vertical_separator)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), 6 * mm),
            ("LEFTPADDING", (1, 0), (1, 0), 6 * mm), ("RIGHTPADDING", (1, 0), (1, 0), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return table

    def _pattern_balance(self, pattern: Mapping[str, Any]) -> list[Any]:
        resolution = pattern["interpretation"].get("resolution")
        if not resolution:
            return []
        sign = str((pattern.get("emptyLeg") or {}).get("sign") or "")
        sign = SIGN_NAMES.get(sign, sign)
        symbols = dict(zip(SIGN_NAMES.values(), "♈♉♊♋♌♍♎♏♐♑♒♓"))
        heading = "Finding Balance"
        if sign:
            heading += f" · {xml_text(sign)} <font name='{self.symbol_font}'>{symbols.get(sign, '')}</font>"
        return [Spacer(1, 6 * mm), self._corner_panel(self._cream_panel([
            Paragraph(heading, self.styles["pattern_balance_heading"]),
            Spacer(1, 2 * mm),
            Paragraph(xml_text(resolution), self.styles["aspect_description"]),
        ]), 18 * mm)]

    def _corner_panel(self, panel: PanelTable, size: float) -> PanelTable:
        panel.setStyle(TableStyle([
            ("CORNERARTWORK", self.palette["corner_artwork"], size),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9 * mm),
        ]))
        return panel

    def _pattern_practice(self, pattern: Mapping[str, Any]) -> list[Any]:
        steps = pattern["interpretation"].get("actionSteps") or []
        if not steps:
            return []
        rows = []
        for start in range(0, len(steps), 3):
            cells = [Paragraph(xml_text(step), self.styles["pattern_practice_body"]) for step in steps[start:start + 3]]
            cells.extend([""] * (3 - len(cells)))
            rows.append(cells)
        table = OrnamentColumns(rows, colWidths=[self.panel_width / 3] * 3, separator_image=self.vertical_separator)
        gold = self.theme["design_system"]["artwork"]["frame"]["color"]
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4 * mm),
            ("LEFTPADDING", (0, 0), (0, -1), 0),
            ("RIGHTPADDING", (2, 0), (2, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return [Spacer(1, 4 * mm),
                Paragraph("Put it into practice", self.styles["pattern_balance_heading"]),
                Spacer(1, 3 * mm), table]

    def _pattern_heading(self, pattern: Mapping[str, Any]) -> Table:
        center_width = self.panel_width - 44 * mm
        center: list[Any] = []
        title = pattern["interpretation"].get("title")
        if title:
            center.append(Paragraph(xml_text(title), self.styles["pattern_title"]))
        display_name = str(pattern.get("patternDisplayName") or "")
        if display_name:
            display = "".join(f"<font name='{self.symbol_font}'>{char}</font>" if char in "☉☽☿♀♂♃♄♅♆♇" else xml_text(char) for char in display_name)
            center.extend([Spacer(1, 2 * mm), Paragraph(display, self.styles["pattern_display_name"])])
        keywords = self.theme["pattern_keywords"].get(pattern.get("type"))
        if keywords:
            center.extend([Spacer(1, 3 * mm), PatternKeywords(keywords, center_width,
                          self.styles["pattern_keyword"], self.palette["panel_surface"],
                          self.theme["design_system"]["artwork"]["frame"]["color"])])
        table = Table([[RasterArtwork(self.pattern_branch_left, 20 * mm, 28 * mm), center,
                        RasterArtwork(self.pattern_branch, 20 * mm, 28 * mm)]],
                      colWidths=[22 * mm, center_width, 22 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return table

    def _sign_cell(self, sign_key: str) -> Paragraph:
        sign = SIGN_NAMES.get(sign_key, sign_key or "-")
        symbols = dict(zip(SIGN_NAMES.values(), "♈♉♊♋♌♍♎♏♐♑♒♓"))
        text = f"<font name='{self.symbol_font}'>{symbols.get(sign, '')}</font> {xml_text(sign)}"
        return Paragraph(text, self.styles["positions_cell"])

    def _positions_table(self, rows, fractions) -> Table:
        table = PanelTable(rows, colWidths=[self.panel_width * fraction for fraction in fractions], repeatRows=1)
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BACKGROUND", (0, 0), (-1, -1), translucent_color(self.palette["panel_surface"], 0.30)),
            ("BORDERWIDTH", 0.9),
            ("BORDERGRADIENT", self.palette["border_gradient_colors"], self.palette["border_gradient_locations"]),
            ("GRADIENTROWS",),
            ("ROUNDEDCORNERS", [5, 5, 5, 5]),
            ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ]))
        return table

    def _positions_story(self) -> list[Any]:
        copy = self.theme["positions_page"]
        intro: list[Any] = []
        for index, text in enumerate(copy["paragraphs"]):
            if index:
                intro.append(Spacer(1, 3 * mm))
            intro.append(Paragraph(xml_text(text), self.styles["aspect_description"]))
        headers = ["Planet", "Sign", "Degree", "Longitude", "Speed", "House", "Retrograde"]
        rows = [[Paragraph(label, self.styles["positions_heading"]) for label in headers]]

        def number(value: Any, places: int, suffix: str = "") -> str:
            return "-" if value is None else f"{float(value):.{places}f}{suffix}"

        for point in self.data.chart.get("planetary_positions") or []:
            values = [point.get("name") or "-",
                      SIGN_NAMES.get(point.get("sign"), point.get("sign") or "-"),
                      number(point.get("degree"), 2, "°"),
                      number(point.get("absolute_longitude"), 2, "°"),
                      number(point.get("speed"), 4),
                      str(point.get("house") if point.get("house") is not None else "-")]
            row = [Paragraph(xml_text(value), self.styles["positions_cell"]) for value in values]
            row[1] = self._sign_cell(point.get("sign"))
            row.append(Paragraph("℞" if point.get("is_retrograde") is True else "-", self.styles["positions_retrograde"]))
            rows.append(row)
        fractions = [0.14, 0.18, 0.13, 0.15, 0.14, 0.10, 0.16]
        table = self._positions_table(rows, fractions)
        return [*page_heading(copy["title"], self.styles, self.palette, self.panel_width), self._cream_panel(intro), Spacer(1, 8 * mm), table]

    def _house_cusps_story(self) -> list[Any]:
        copy = self.theme["house_cusps_page"]
        intro: list[Any] = []
        for index, text in enumerate(copy["paragraphs"]):
            if index:
                intro.append(Spacer(1, 3 * mm))
            intro.append(Paragraph(xml_text(text), self.styles["aspect_description"]))
        rows = [[Paragraph(text, self.styles["positions_heading"]) for text in
                 ("House Number", "Ruler (sign)", "Degree", "Longitude", "Type")]]
        for house in self.data.chart.get("house_cusps") or []:
            number = int(house["house"])
            if not 1 <= number <= 12:
                raise ValueError("House must be 1–12")
            kind = ("Angular", "Succedent", "Cadent")[(number - 1) % 3]
            values = [str(number), "", f"{float(house['degree']):.2f}°",
                      f"{float(house['absolute_longitude']):.2f}°", kind]
            row = [Paragraph(xml_text(value), self.styles["positions_cell"]) for value in values]
            row[1] = self._sign_cell(house.get("sign"))
            rows.append(row)
        return [*page_heading(copy["title"], self.styles, self.palette, self.panel_width),
                self._cream_panel(intro), Spacer(1, 8 * mm),
                self._positions_table(rows, [0.20, 0.24, 0.17, 0.20, 0.19])]

    def _portrait_story(self) -> list[Any]:
        """Render either fallback text or the structured interpretation DTO."""
        import json

        def decode(value: Any) -> Any:
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (ValueError, TypeError):
                    return value
            return value

        def content(value: Any) -> list[Any]:
            value = decode(value)
            if isinstance(value, str):
                paragraphs, question = value.split("\n\n"), None
            elif isinstance(value, Mapping):
                paragraphs = value.get("paragraphs") or []
                if isinstance(paragraphs, str):
                    paragraphs = [paragraphs]
                question = value.get("reflectionQuestion")
            else:
                return []
            result: list[Any] = []
            for text in paragraphs:
                if isinstance(text, str) and text.strip():
                    result.append(Paragraph(xml_text(text.strip()), self.styles["portrait_body"]))
            if isinstance(question, str) and question.strip():
                result.append(Paragraph(f"<b>Reflection:</b> {xml_text(question.strip())}", self.styles["portrait_reflection"]))
            return result

        interpretation = decode(self.data.interpretation_text)
        heading = lambda: page_heading("Your Celestial Portrait", self.styles, self.palette, self.panel_width)

        def separator() -> list[Any]:
            return [Spacer(1, 5 * mm), self._ornate_separator(self.panel_width, 12 * mm),
                    Spacer(1, 5 * mm)]

        def boxed(items: list[Any]) -> PanelTable:
            panel = PanelTable([[items]], colWidths=[self.panel_width], minRowHeights=[45 * mm])
            panel.setStyle(TableStyle([
                *panel_box_style(self.palette),
                ("CORNERARTWORK", self.palette["corner_artwork"], 28 * mm),
                ("EXTRACORNERARTWORK", self.palette["corner_artwork_bottom_left"], 28 * mm, "bottom_left"),
                ("LEFTPADDING", (0, 0), (-1, -1), 9 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 10 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10 * mm),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            return panel

        if not isinstance(interpretation, Mapping):
            fallback = content(interpretation)
            return [*heading(), boxed(fallback)] if fallback else []

        pages: list[list[Any]] = []
        for keys, trailing_separator in ((
                (("opening", None), ("coreStrengths", "Core Strengths"),
                 ("growthOpportunities", "Growth Opportunities")), False),
                ((("lifePurpose", "Life Purpose"), ("soulDirection", "Soul Direction"),
                  ("closing", None)), False)):
            sections: list[list[Any]] = []
            for key, title in keys:
                items = content(interpretation.get(key))
                if items:
                    sections.append([Paragraph(title, self.styles["portrait_heading"]), *items]
                                    if title else [boxed(items)])
            if sections:
                page = [*heading(), Spacer(1, 3 * mm)]
                for index, section in enumerate(sections):
                    page.extend(section)
                    if index < len(sections) - 1 or trailing_separator:
                        page.extend(separator())
                pages.append(page)
        story: list[Any] = []
        for index, page in enumerate(pages):
            if index:
                story.append(PageBreak())
            story.extend(page)
        return story

    def _patterns_story(self) -> list[Any]:
        copy = self.theme["patterns_page"]
        story: list[Any] = [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
        ]
        intro: list[Any] = []
        for index, text in enumerate(copy["paragraphs"]):
            if index:
                intro.append(Spacer(1, 3 * mm))
            intro.append(Paragraph(xml_text(text), self.styles["aspect_description"]))
        story.append(self._cream_panel(intro))
        story.extend([self._ornate_separator(self.panel_width, 10 * mm), Spacer(1, 3 * mm)])
        for pattern in self.data.patterns:
            interpretation = pattern["interpretation"]
            content: list[Any] = [self._pattern_heading(pattern), Spacer(1, 3 * mm)]
            if interpretation.get("summary"):
                content.append(Paragraph(xml_text(interpretation["summary"]), self.styles["pattern_summary"]))
            content.extend([Spacer(1, 5 * mm), self._pattern_details(pattern)])
            content.extend(self._pattern_balance(pattern))
            content.extend(self._pattern_practice(pattern))
            if content:
                story.append(KeepTogether(content))
        return story

    def _aspects_intro_story(self) -> list[Any]:
        copy = self.theme["aspects_intro"]
        story: list[Any] = [
            *page_heading(copy["title"], self.styles, self.palette, self.panel_width),
        ]
        for index, text in enumerate(copy["paragraphs"]):
            if index:
                story.extend([Spacer(1, 6 * mm), self._paired_separator(), Spacer(1, 6 * mm)])
            panel = PanelTable([[Paragraph(xml_text(text), self.styles["aspects_intro_body"])]],
                          colWidths=[self.panel_width])
            panel.setStyle(TableStyle([
                *panel_box_style(self.palette),
                ("CORNERARTWORK", self.palette["corner_artwork_bottom_right"], 16 * mm, "bottom_right"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 5 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5 * mm),
            ]))
            story.append(panel)
        return story

    def _cover_birth_line(self) -> str:
        user = self.data.user
        raw_date = str(user.get("birthDate") or "")
        try:
            parsed_date = datetime.strptime(raw_date, "%Y-%m-%d")
            birth_date = f"{parsed_date.day} {parsed_date.strftime('%B %Y')}"
        except ValueError:
            birth_date = raw_date
        birth_time = str(user.get("birthTime") or "").removesuffix(":00")
        place = ", ".join(filter(None, (str(user.get("birthCity") or ""), str(user.get("birthCountryCode") or ""))))
        return "  ·  ".join(filter(None, (birth_date, birth_time, place)))

    def _cover_big_three_line(self) -> str:
        entries: list[str] = []
        for key, label, symbol in (("sun", "SUN", "☉"), ("moon", "MOON", "☽"), ("ascendant", "ASC", "")):
            point = self.data.subject.get(key) or {}
            sign_key = str(point.get("sign") or "")
            sign_name = SIGN_NAMES.get(sign_key, sign_key).upper() or "—"
            glyph = f"<font name='{self.symbol_font}'>{symbol}</font>&nbsp; " if symbol else ""
            entries.append(
                f"{glyph}<font name='Helvetica'>{label} ·</font>&nbsp; {xml_text(sign_name)}"
            )
        return "&nbsp;&nbsp;&nbsp;&nbsp;".join(entries)

    def _cover_story(self) -> list[Any]:
        separator = self._ornate_separator(self.page_size[0] - 52 * mm, 18 * mm)
        separator.hAlign = "CENTER"
        return [
            Spacer(1, 57 * mm),
            Paragraph(xml_text(self.theme["document"]["title"].upper()), self.styles["cover_title"]),
            Spacer(1, 2.5 * mm),
            Paragraph(xml_text(self.theme["document"].get("subtitle", "")), self.styles["cover_tagline"]),
            Spacer(1, 4 * mm),
            separator,
            Spacer(1, 11 * mm),
            Paragraph(xml_text(self.theme["labels"]["generated_for"]), self.styles["cover_prepared"]),
            Spacer(1, 1.5 * mm),
            Paragraph(xml_text(self.data.name), self.styles["cover_name"]),
            Spacer(1, 5 * mm),
            Paragraph(xml_text(self._cover_birth_line()), self.styles["cover_birth_data"]),
            Spacer(1, 5 * mm),
            Paragraph(self._cover_big_three_line(), self.styles["cover_big_three"]),
            Spacer(1, 51 * mm),
            Paragraph("by Venastella", self.styles["cover_signature"]),
            PageBreak(),
        ]

    def _ending_story(self) -> list[Any]:
        copy = self.theme["ending_page"]
        width = self.page_size[0] - 50 * mm - 2 * self.body_frame_padding
        story: list[Any] = [*page_heading(copy["title"], self.styles, self.palette, width)]
        opening = [Paragraph(xml_text(text), self.styles["ending_body"])
                   for text in copy["opening_paragraphs"]]
        panel = PanelTable([[opening]], colWidths=[width])
        panel.setStyle(TableStyle([
            *panel_box_style(self.palette),
            ("LEFTPADDING", (0, 0), (-1, -1), 5 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 5 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        story.append(panel)

        def separator() -> None:
            story.extend([Spacer(1, 3 * mm),
                          self._ornate_separator(self.page_size[0] - 60 * mm, 12 * mm),
                          Spacer(1, 3 * mm)])

        separator()
        story.extend([
            Paragraph(xml_text(copy["prepared_label"]), self.styles["cover_prepared"]),
            Spacer(1, 2 * mm),
            Paragraph(xml_text(self.data.name), self.styles["cover_name"]),
            Spacer(1, 4 * mm),
            Paragraph(self._cover_big_three_line(), self.styles["cover_big_three"]),
        ])
        separator()
        story.append(Paragraph(xml_text(copy["disclaimer"]), self.styles["ending_disclaimer"]))
        separator()
        story.extend([
            Paragraph("Venastella", self.styles["ending_brand"]),
            Spacer(1, 2 * mm),
            Paragraph(xml_text(copy["brand_description"]), self.styles["ending_brand_body"]),
        ])
        try:
            generated = datetime.fromisoformat(self.data.created_at.replace("Z", "+00:00"))
            if generated.tzinfo:
                generated = generated.astimezone(ZoneInfo("Europe/London"))
        except ValueError:
            generated = datetime.now(ZoneInfo("Europe/London"))
        date_label = f"Generated on {generated.day} {generated.strftime('%B %Y')}"
        story.extend([Spacer(1, 6 * mm),
                      Paragraph(xml_text(date_label), self.styles["ending_date"])])
        return story

    def build(self) -> None:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        margin = float(self.theme["document"].get("margin_mm", 17)) * mm
        doc = BaseDocTemplate(str(self.output), pagesize=self.page_size, leftMargin=margin, rightMargin=margin, topMargin=18 * mm, bottomMargin=17 * mm)
        doc.addPageTemplates([
            PageTemplate(id="Cover", frames=Frame(20 * mm, 20 * mm, self.page_size[0] - 40 * mm, self.page_size[1] - 40 * mm, id="cover"), onPage=self._cover_page, autoNextPageTemplate="Welcome"),
            PageTemplate(id="Welcome", frames=Frame(30 * mm, 17 * mm, self.page_size[0] - 60 * mm, self.page_size[1] - 34 * mm, id="welcome"), onPage=self._welcome_page, autoNextPageTemplate="Body"),
            PageTemplate(id="Body", frames=Frame(self.body_frame_inset, self.body_frame_inset, self.page_size[0] - 2 * self.body_frame_inset, self.page_size[1] - 2 * self.body_frame_inset, id="body"), onPage=self._body_page),
            PageTemplate(id="Ending", frames=Frame(25 * mm, 20 * mm, self.page_size[0] - 50 * mm, self.page_size[1] - 40 * mm, id="ending"), onPage=self._cover_page),
        ])
        story = self._cover_story()
        story.extend(self._welcome_story())
        story.append(PageBreak())
        story.extend(self._chart_story())
        story.append(PageBreak())
        story.extend(self._big_three_story())
        story.append(PageBreak())
        aggregate_story = self._aggregate_story()
        if aggregate_story:
            story.extend(aggregate_story)
            story.append(PageBreak())
        story.extend(self._core_identity_story())
        story.append(PageBreak())
        story.extend(self._moon_ascendant_story())
        story.append(PageBreak())
        story.extend(self._midheaven_story())
        story.append(PageBreak())
        story.extend(self._personal_planets_mercury_story())
        story.append(PageBreak())
        story.extend(self._personal_planets_venus_mars_story())
        story.append(PageBreak())
        story.extend(self._social_planets_story())
        story.append(PageBreak())
        story.extend(self._generational_points_story())
        story.append(PageBreak())
        story.extend(self._additional_points_story("healing_relationships", "chiron", "descendant"))
        story.append(PageBreak())
        story.extend(self._additional_points_story("roots_change", "imum_coeli", "uranus"))
        story.append(PageBreak())
        story.extend(self._additional_points_story("outer_planets", "neptune", "pluto"))
        story.append(PageBreak())
        # Present the twelve houses in six pairs.
        for first in range(1, 13, 2):
            if first > 1:
                story.append(PageBreak())
            story.extend(self._houses_story(first, first + 1, intro=first == 1))
        if self.data.aspects:
            story.append(PageBreak())
            story.extend(self._aspects_intro_story())
            story.append(PageBreak())
            story.extend(AspectSection(self.data.aspects, self.styles, self.palette,
                                       self.symbol_font, self.panel_width).build())
        if self.data.patterns:
            story.append(PageBreak())
            story.extend(self._patterns_story())
        portrait = self._portrait_story()
        if portrait:
            story.append(PageBreak())
            story.extend(portrait)
        if self.data.chart.get("planetary_positions"):
            story.append(PageBreak())
            story.extend(self._positions_story())
        if self.data.chart.get("house_cusps"):
            story.append(PageBreak())
            story.extend(self._house_cusps_story())
        story.extend([NextPageTemplate("Ending"), PageBreak(), *self._ending_story()])
        doc.build(story, canvasmaker=lambda *args, **kwargs:
                  NumberedCanvas(*args, footer_style=self.styles["footer"], **kwargs))
