"""Checkout contains only an internal reference; birth details stay in Django."""
import stripe
from django.conf import settings
from django.urls import reverse


class CheckoutAlreadyCompleted(Exception):
    pass


def checkout_configuration_error():
    if settings.PAYMENT_MODE == 'demo':
        return '' if settings.DEBUG else 'Demo checkout is unavailable.'
    if not (settings.STRIPE_SECRET_KEY and settings.STRIPE_WEBHOOK_SECRET):
        return 'Checkout is temporarily unavailable. Stripe credentials need configuring.'
    expected = ('sk_test_', 'rk_test_') if settings.PAYMENT_MODE == 'test' else ('sk_live_', 'rk_live_')
    if not settings.STRIPE_SECRET_KEY.startswith(expected):
        return 'Checkout is temporarily unavailable. The Stripe key does not match the payment mode.'
    if settings.PAYMENT_MODE == 'live':
        from .invoicing import live_invoice_ready
        if not live_invoice_ready():
            return 'Checkout is temporarily unavailable. Business invoice details need configuring.'
    return ''


def create_checkout(birth_request):
    client = stripe.StripeClient(settings.STRIPE_SECRET_KEY)
    attempt = 'initial'
    if birth_request.stripe_session_id:
        existing = client.v1.checkout.sessions.retrieve(birth_request.stripe_session_id)
        if existing.status == 'open':
            return existing
        if existing.status == 'complete':
            raise CheckoutAlreadyCompleted()
        attempt = existing.id
    return client.v1.checkout.sessions.create({
        'mode': 'payment',
        **({'customer_email': birth_request.email} if birth_request.email else {}),
        'payment_method_types': ['card'],
        'billing_address_collection': 'required',
        'client_reference_id': str(birth_request.id),
        'metadata': {'birth_request_id': str(birth_request.id)},
        'line_items': [{'price_data': {'currency': birth_request.currency, 'unit_amount': birth_request.amount_pence, 'product_data': {'name': 'Venastella natal chart'}}, 'quantity': 1}],
        'success_url': settings.PUBLIC_BASE_URL + reverse('birth-status', args=[birth_request.id]),
        'cancel_url': settings.PUBLIC_BASE_URL + reverse('birth-status', args=[birth_request.id]) + '?cancelled=1',
    }, options={'idempotency_key': f'birth-request-{birth_request.id}-{attempt}'})
