import base64
import json
from io import BytesIO
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader
from .models import BirthRequest, Invoice
from .invoicing import ensure_invoice, invoice_pdf
from .test_checkout import DETAILS


@override_settings(PAYMENT_MODE='demo', DEBUG=True, STRIPE_CHECKOUT_ENABLED=True)
class DemoCheckoutTests(TestCase):
    def test_checkout_does_not_contact_stripe_and_payment_is_explicit(self):
        client = Client(enforce_csrf_checks=True)
        token = client.get('/csrf-token/').json()['token']
        with patch('studio.views.create_checkout') as stripe:
            response = client.post('/natal-chart/', {**DETAILS, 'csrfmiddlewaretoken': token})
            stripe.assert_not_called()
        customer = BirthRequest.objects.get()
        self.assertEqual(customer.status, 'pending')
        self.assertEqual(customer.payment_mode, 'demo')
        self.assertRedirects(response, reverse('demo-checkout', args=[customer.pk]))
        self.assertFalse(Invoice.objects.exists())
        self.assertEqual(Client().get(response.url).status_code, 404)
        self.assertEqual(client.post(response.url).status_code, 403)
        paid = client.post(response.url, {'csrfmiddlewaretoken': token})
        self.assertEqual(paid.status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.status, 'paid')
        invoice = Invoice.objects.get()
        self.assertTrue(invoice.is_test)
        self.assertEqual(invoice.total_pence, 3900)
        client.post(response.url, {'csrfmiddlewaretoken': token})
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertContains(client.get(paid.url), 'Thank you for your business')
        self.assertContains(client.get(paid.url), 'Request removal of my data')
        download = client.get(reverse('invoice-download', args=[customer.pk]))
        self.assertEqual(download['Content-Type'], 'application/pdf')
        text = PdfReader(BytesIO(download.content)).pages[0].extract_text()
        self.assertIn('£39.00', text)
        self.assertIn('TEST INVOICE', text)
        self.assertNotIn('London', text)  # Birth town is never used as billing address.
        self.assertEqual(Client().get(reverse('invoice-download', args=[customer.pk])).status_code, 404)

    @override_settings(DEBUG=False)
    def test_demo_is_blocked_outside_debug(self):
        customer = BirthRequest.objects.create(payload={'name': 'Test'}, payment_mode='demo', status='pending')
        session = self.client.session
        session['birth_requests'] = [str(customer.pk)]
        session.save()
        self.assertEqual(self.client.post(reverse('demo-checkout', args=[customer.pk])).status_code, 404)
        customer.refresh_from_db()
        self.assertEqual(customer.status, 'pending')

    def test_free_redemption_never_has_invoice(self):
        self.client.post('/redeem-free-natal-chart/', DETAILS)
        customer = BirthRequest.objects.get()
        self.assertIsNone(ensure_invoice(customer))
        self.assertEqual(self.client.get(reverse('invoice-download', args=[customer.pk])).status_code, 404)
        self.assertFalse(Invoice.objects.exists())


class InvoiceTests(TestCase):
    @override_settings(INVOICE_VAT_STATUS='registered', INVOICE_VAT_RATE='0.20', INVOICE_VAT_NUMBER='TEST123', INVOICE_BUSINESS_ADDRESS='Example seller address')
    def test_invoice_snapshot_vat_and_one_invoice_per_payment(self):
        customer = BirthRequest.objects.create(payload={'name': 'Test'}, email='test@example.com', status='paid', paid_at=timezone.now(), payment_mode='test')
        invoice = ensure_invoice(customer, {'name': 'Billing name', 'address': {'line1': 'Billing address'}})
        self.assertEqual(invoice.vat_pence, 650)
        with override_settings(INVOICE_BUSINESS_NAME='Changed seller'):
            self.assertEqual(ensure_invoice(customer).pk, invoice.pk)
        invoice.refresh_from_db()
        self.assertEqual(invoice.issuer['name'], 'Venastella')
        pdf = invoice_pdf(invoice)
        self.assertEqual(pdf, invoice_pdf(invoice))
        self.assertEqual(len(PdfReader(BytesIO(pdf)).pages), 1)
        self.assertIn('Billing address', PdfReader(BytesIO(pdf)).pages[0].extract_text())
        self.assertEqual(Invoice.objects.count(), 1)

    @override_settings(PAYMENT_MODE='live', STRIPE_CHECKOUT_ENABLED=True, STRIPE_SECRET_KEY='sk_live_test', STRIPE_WEBHOOK_SECRET='whsec_test', INVOICE_BUSINESS_ADDRESS='')
    def test_live_checkout_requires_real_invoice_details(self):
        self.assertContains(self.client.post('/natal-chart/', DETAILS), 'Business invoice details need configuring')
        self.assertFalse(BirthRequest.objects.exists())

    @override_settings(PAYMENT_MODE='test', STRIPE_CHECKOUT_ENABLED=True, STRIPE_SECRET_KEY='sk_live_test', STRIPE_WEBHOOK_SECRET='whsec_test')
    def test_test_mode_cannot_use_a_live_stripe_key(self):
        self.assertContains(self.client.post('/natal-chart/', DETAILS), 'key does not match')
        self.assertFalse(BirthRequest.objects.exists())
