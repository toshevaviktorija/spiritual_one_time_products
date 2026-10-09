from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape
from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph
from reportlab.pdfgen import canvas
from .models import Invoice, BirthRequest


def live_invoice_ready():
    return bool(settings.INVOICE_BUSINESS_ADDRESS and settings.INVOICE_BUSINESS_NAME and
                settings.INVOICE_VAT_STATUS in ('registered', 'not_registered') and
                (settings.INVOICE_VAT_STATUS != 'registered' or settings.INVOICE_VAT_NUMBER))


def ensure_invoice(customer, billing=None):
    if customer.status != BirthRequest.Status.PAID:
        return None
    billing = billing or {}
    rate = Decimal(settings.INVOICE_VAT_RATE) if settings.INVOICE_VAT_STATUS == 'registered' else Decimal(0)
    gross = Decimal(customer.amount_pence)
    net = (gross / (1 + rate)).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    invoice, _ = Invoice.objects.get_or_create(birth_request=customer, defaults={
        'issued_at': customer.paid_at or timezone.now(),
        'line_items': [{'description': 'Personalised natal chart PDF', 'quantity': 1, 'unit_net_pence': int(net), 'line_net_pence': int(net)}],
        'contract_terms': customer.delivery_consent, 'payment_reference': customer.stripe_session_id or '',
        'customer': {'name': billing.get('name') or customer.payload.get('name', ''),
                     'email': customer.email, 'address': billing.get('address') or {}},
        'issuer': {'name': settings.INVOICE_BUSINESS_NAME, 'address': settings.INVOICE_BUSINESS_ADDRESS,
                   'email': settings.INVOICE_BUSINESS_EMAIL, 'vat_status': settings.INVOICE_VAT_STATUS,
                   'vat_number': settings.INVOICE_VAT_NUMBER, 'vat_rate': str(rate)},
        'total_pence': customer.amount_pence, 'vat_pence': int(gross - net),
        'currency': customer.currency, 'is_test': customer.payment_mode != 'live',
    })
    return invoice


def invoice_pdf(invoice):
    stream = BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4, invariant=1)
    width, height = A4
    bg, surface, gold, text = map(colors.HexColor, ['#100820', '#28183E', '#D9AA68', '#F4E8DD'])
    pdf.setTitle(f'Venastella invoice {invoice.number}')
    pdf.setFillColor(bg)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.drawImage(str(settings.BASE_DIR / 'assets/product/logo.png'), 44, height - 130, width=78, height=78, mask='auto')
    pdf.setFillColor(gold)
    pdf.setFont('Times-Roman', 26)
    pdf.drawString(139, height - 78, 'VENASTELLA')
    pdf.setFont('Helvetica', 10)
    pdf.drawString(140, height - 101, 'A little map of your inner universe.')
    pdf.setFont('Helvetica-Bold', 12)
    pdf.drawRightString(width - 44, height - 157, 'INVOICE')
    pdf.setFillColor(surface)
    pdf.setStrokeColor(gold)
    pdf.roundRect(44, 155, width - 88, height - 335, 14, fill=1, stroke=1)
    def paragraph(value, x, top, max_width, size=10, color=text):
        style = ParagraphStyle('invoice', fontName='Helvetica', fontSize=size, leading=size * 1.5, textColor=color)
        item = Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
        _, item_height = item.wrap(max_width, 600)
        item.drawOn(pdf, x, top - item_height)
        return top - item_height
    top = height - 200
    paragraph('FROM', 65, top, 210, 9, gold)
    paragraph('BILL TO', 320, top, 205, 9, gold)
    issuer_text = invoice.issuer['name'] + '\n' + (invoice.issuer['address'] or 'Business address: not configured') + '\n' + invoice.issuer['email']
    if invoice.issuer.get('vat_number'):
        issuer_text += '\nVAT: ' + invoice.issuer['vat_number']
    address = invoice.customer.get('address') or {}
    billing_text = invoice.customer['name'] + '\n' + invoice.customer['email']
    billing_text += '\n' + '\n'.join(str(address.get(k)) for k in ['line1', 'line2', 'city', 'state', 'postal_code', 'country'] if address.get(k))
    if not address:
        billing_text += '\nBilling address: not provided (test)'
    y1 = paragraph(issuer_text, 65, top - 24, 210)
    y2 = paragraph(billing_text, 320, top - 24, 205)
    y = min(y1, y2) - 28
    paragraph('Invoice number: ' + invoice.number, 65, y, 220)
    paragraph('Invoice date: ' + timezone.localtime(invoice.issued_at).strftime('%d %B %Y'), 320, y, 205)
    y -= 48
    pdf.setStrokeColor(colors.HexColor('#6F477A'))
    pdf.line(65, y, width - 65, y)
    paragraph('DESCRIPTION', 65, y - 15, 235, 9, gold)
    paragraph('QTY', 344, y - 15, 40, 9, gold)
    paragraph('AMOUNT', 426, y - 15, 110, 9, gold)
    net_pence = invoice.total_pence - invoice.vat_pence
    paragraph((invoice.line_items or [{'description': 'Personalised natal chart PDF'}])[0]['description'], 65, y - 48, 265, 12)
    paragraph(str((invoice.line_items or [{'quantity': 1}])[0]['quantity']), 350, y - 48, 40, 12)
    paragraph(f'£{net_pence / 100:.2f} GBP', 426, y - 48, 110, 12)
    y -= 110
    pdf.line(65, y, width - 65, y)
    vat_text = f'VAT ({Decimal(invoice.issuer.get("vat_rate", "0")) * 100:g}%): £{invoice.vat_pence / 100:.2f}' if invoice.issuer.get('vat_status') == 'registered' else ('Not VAT registered' if invoice.issuer.get('vat_status') == 'not_registered' else 'VAT status: not configured - test only')
    paragraph(vat_text, 65, y - 16, 340, 9)
    paragraph(f'TOTAL  £{invoice.total_pence / 100:.2f} GBP', 300, y - 53, 245, 19, gold)
    paragraph('PAID (SIMULATED)' if invoice.is_test else 'PAID', 300, y - 88, 245, 10, gold)
    paragraph('Thank you for your business and for choosing Venastella.', 65, 128, width - 130, 11, gold)
    paragraph('Your sky. Your story.', 65, 105, width - 130, 10)
    if invoice.is_test:
        paragraph('TEST INVOICE - NO REAL PAYMENT - NOT FOR ACCOUNTING USE', 44, 54, width - 88, 9, gold)
    pdf.showPage()
    pdf.save()
    return stream.getvalue()
