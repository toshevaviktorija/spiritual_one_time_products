"""Shared report-page heading geometry and title-width underline."""
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, Spacer, HRFlowable
from ..flowables import color
from .formatting import xml_text


def page_heading(text, styles, palette, width):
    text = text.upper()
    style = styles['title']
    line_width = min(width, pdfmetrics.stringWidth(text, style.fontName, style.fontSize))
    return [Spacer(1, mm), Paragraph(xml_text(text), style), Spacer(1, 2 * mm),
            HRFlowable(width=line_width, thickness=0.8, color=color(palette['ornament_gold']), hAlign='CENTER'),
            Spacer(1, 4 * mm)]
