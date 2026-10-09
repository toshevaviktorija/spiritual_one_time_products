import base64
import hashlib
import json
from datetime import timedelta
from django.utils import timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from .validators import validate_delivery_email
from .terms import REFUND_TERMS


class ChartEmailError(Exception):
    pass


def pdf_content(report):
    path = settings.PRIVATE_REPORT_ROOT / f'{report.id}.pdf'
    try:
        content = path.read_bytes()
    except OSError:
        raise ChartEmailError('The PDF is unavailable. Generate a new report before sending.')
    if not content.startswith(b'%PDF-'):
        raise ChartEmailError('The attachment is not a PDF. Generate a new report.')
    if len(content) > 20 * 1024 * 1024:
        raise ChartEmailError('The PDF exceeds the 20 MB attachment limit.')
    return content


def reviews_url():
    return settings.PUBLIC_BASE_URL + reverse('reviews')


def removal_url(draft):
    customer = getattr(draft, 'birth_request', None)
    return settings.PUBLIC_BASE_URL + reverse('data-removal', args=[customer.removal_token]) if customer else ''


def email_html(draft):
    customer = getattr(draft, 'birth_request', None)
    return render_to_string('studio/email/chart.html', {'draft': draft, 'reviews_url': reviews_url(), 'removal_url': removal_url(draft), 'has_invoice': bool(customer and customer.status == 'paid'), 'refund_terms': (customer.delivery_consent.get('refund_terms') or REFUND_TERMS) if customer and customer.source == 'storefront' else '', 'delivery_consent': customer.delivery_consent.get('consent', '') if customer else ''})


def submit_email(draft):
    if not settings.RESEND_API_KEY or not draft.sender:
        raise ChartEmailError('Configure RESEND_API_KEY and a verified RESEND_FROM_EMAIL before sending.')
    validate_delivery_email(draft.recipient)
    validate_delivery_email(draft.sender)
    if draft.reply_to:
        validate_delivery_email(draft.reply_to)
    if timezone.now() - draft.created_at > timedelta(hours=23):
        raise ChartEmailError('This preview has expired. Check Resend for an earlier submission before creating a new preview.')
    if draft.report.birth_request_id != draft.birth_request_id:
        raise ChartEmailError('This PDF no longer belongs to this request. Create a new preview with the correct attachment.')
    from .models import DataRemovalRequest
    if DataRemovalRequest.objects.filter(email__iexact=draft.recipient, approved_at__isnull=True).exists():
        raise ChartEmailError('This customer has requested data removal. Review that request before sending.')
    content = pdf_content(draft.report)
    if hashlib.sha256(content).hexdigest() != draft.pdf_sha256:
        raise ChartEmailError('The PDF changed after preview. Create a new email preview and inspect it again.')
    payload = {'from': f'Venastella <{draft.sender}>', 'to': [draft.recipient],
               'subject': draft.subject, 'html': email_html(draft),
               'text': draft.message + '\n\nOnce you’ve had a moment to explore your chart, we’d love to hear what you think. Please share a review: ' + reviews_url() + '\n\nWith love and starlight,\nVenastella\nA little map of your inner universe.',
               'attachments': [{'filename': 'Venastella_Natal_Chart.pdf', 'content': base64.b64encode(content).decode()}]}
    payload['text'] += '\n\nYour data stays private. We retain your name, email, birth details, billing details and request/delivery/invoice records. Chart inputs are processed temporarily; the PDF is held for preparation and inspection and removed from this website after email submission. Resend processes email delivery. Already-delivered emails and downloaded copies are separate.\nRequest removal of my data (reviewed in our admin panel): ' + removal_url(draft)
    if draft.birth_request.status == 'pending':
        raise ChartEmailError('Confirm payment before delivering the chart.')
    if draft.birth_request.source == 'storefront':
        payload['text'] += '\n\n' + (draft.birth_request.delivery_consent.get('refund_terms') or REFUND_TERMS)
        if draft.birth_request.delivery_consent:
            payload['text'] += '\nYour recorded agreement: ' + draft.birth_request.delivery_consent.get('consent', '')
    payload['text'] += '\nLegally required invoice and transaction records are retained for accounting after a data-removal request.'
    if draft.birth_request.status == 'paid':
        from .invoicing import ensure_invoice, invoice_pdf
        invoice = ensure_invoice(draft.birth_request)
        payload['attachments'].append({'filename': f'Venastella_Invoice_{invoice.number}.pdf', 'content': base64.b64encode(invoice_pdf(invoice)).decode()})
        payload['text'] += '\n\nThank you for your business. Your PDF invoice is also attached.'
        if invoice.is_test:
            payload['subject'] = '[TEST PAYMENT] ' + payload['subject']
            payload['text'] += '\nTEST INVOICE - no real payment was taken.'
    if draft.reply_to:
        payload['reply_to'] = draft.reply_to
    request = Request('https://api.resend.com/emails', data=json.dumps(payload).encode(), method='POST',
                      headers={'Authorization': f'Bearer {settings.RESEND_API_KEY}', 'Content-Type': 'application/json',
                               'User-Agent': 'Venastella/1.0', 'Idempotency-Key': f'chart-email/{draft.id}'})
    try:
        with urlopen(request, timeout=30) as response:
            result = json.load(response)
    except HTTPError as error:
        raise ChartEmailError(f'Resend rejected the email (HTTP {error.code}). Check the verified sender and API key, then retry this preview.') from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise ChartEmailError('Resend could not confirm submission. Retry this same preview to avoid sending a duplicate.') from None
    if not isinstance(result, dict) or not result.get('id'):
        raise ChartEmailError('Resend did not confirm submission. Retry this same preview.')
    return result['id']
