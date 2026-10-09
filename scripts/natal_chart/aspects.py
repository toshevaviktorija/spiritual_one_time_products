"""Grouped aspect interpretations, with each pair kept beside its meaning."""

from collections import OrderedDict
from math import isfinite

from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

from .flowables import PanelTable, panel_box_style
from .utilities.formatting import xml_text
from .utilities.page_heading import page_heading


class AspectSection:
    def __init__(self, aspects, styles, palette, symbol_font, width):
        self.aspects, self.styles, self.palette = aspects, styles, palette
        self.symbol_font, self.width = symbol_font, width

    def _symbol(self, value):
        return f"<font name='{self.symbol_font}'>{xml_text(value or '')}</font>"

    def _pair(self, item):
        first, second, aspect = item['point1'], item['point2'], item['aspect']
        heading = ' &nbsp; '.join([
            self._symbol(first.get('symbol')),
            xml_text(first.get('name') or first.get('id') or ''),
            self._symbol(aspect.get('symbol')),
            self._symbol(second.get('symbol')),
            xml_text(second.get('name') or second.get('id') or ''),
        ])
        try:
            orb = abs(float(item['orb']))
            orb_text = f'Orb {orb:.2f}°' if isfinite(orb) else ''
        except (KeyError, TypeError, ValueError):
            orb_text = ''
        header = Table([[
            Paragraph(heading, self.styles['aspect_pair']),
            Paragraph(orb_text, self.styles['aspect_orb']),
        ]], colWidths=[self.width - 31 * mm, 31 * mm])
        header.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        content = [header, Spacer(1, 2 * mm)]
        interpretation = item['interpretation']
        if interpretation.get('title'):
            content.extend([Paragraph(xml_text(interpretation['title']), self.styles['aspect_pair']), Spacer(1, 1 * mm)])
        if interpretation.get('meaning'):
            content.append(Paragraph(xml_text(interpretation['meaning']), self.styles['aspect_meaning']))
        content.append(Spacer(1, 6 * mm))
        return content

    def build(self):
        groups = OrderedDict()
        for item in self.aspects:
            aspect = item['aspect']
            key = str(aspect.get('type') or aspect.get('name') or 'Aspect').strip().lower()
            groups.setdefault(key, []).append(item)
        story = []
        for index, (key, items) in enumerate(groups.items()):
            if index:
                story.append(PageBreak())
            aspect = items[0]['aspect']
            name = aspect.get('name') or key.title()
            heading = f"{self._symbol(aspect.get('symbol'))} &nbsp; {xml_text(name)}s"
            intro = [*page_heading('Aspects', self.styles, self.palette, self.width),
                     Paragraph(heading, self.styles['aspect_group'])]
            description = next((i['interpretation'].get('description') for i in items if i['interpretation'].get('description')), '')
            if description:
                panel = PanelTable([[Paragraph(xml_text(description), self.styles['aspect_description'])]], colWidths=[self.width])
                panel.setStyle(TableStyle([
                    *panel_box_style(self.palette),
                    ("CORNERARTWORK", self.palette["corner_artwork_bottom_right"], 13 * mm, "bottom_right"),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4 * mm),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 8 * mm),
                    ('TOPPADDING', (0, 0), (-1, -1), 4 * mm),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4 * mm),
                ]))
                intro.extend([panel, Spacer(1, 7 * mm)])
            story.append(KeepTogether(intro + self._pair(items[0])))
            story.extend(KeepTogether(self._pair(item)) for item in items[1:])
        return story
