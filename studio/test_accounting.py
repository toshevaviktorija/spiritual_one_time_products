from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import BirthRequest, Invoice, DataRemovalRequest
from .invoicing import ensure_invoice, invoice_pdf
from .privacy import remove_customer
from .terms import DELIVERY_CONSENT, REFUND_TERMS
from .test_checkout import DETAILS


class AccountingTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_superuser('accountant', 'accountant@example.com', 'test-password')

    @override_settings(PAYMENT_MODE='demo', DEBUG=True, STRIPE_CHECKOUT_ENABLED=True)
    def test_explicit_unchecked_delivery_consent_required_and_recorded(self):
        missing = dict(DETAILS)
        missing.pop('early_delivery_consent')
        response = self.client.post('/natal-chart/', missing)
        self.assertContains(response, 'Please confirm the digital delivery')
        self.assertFalse(BirthRequest.objects.exists())
        page = self.client.get('/natal-chart/').content.decode()
        self.assertIn('name="early_delivery_consent"', page)
        self.assertNotIn('name="early_delivery_consent" checked', page)
        self.client.post('/natal-chart/', DETAILS)
        customer = BirthRequest.objects.get()
        self.assertEqual(customer.delivery_consent['consent'], DELIVERY_CONSENT)
        self.assertEqual(customer.delivery_consent['refund_terms'], REFUND_TERMS)
        self.assertTrue(customer.delivery_consent['accepted_at'])
        customer.status = 'paid'
        customer.paid_at = timezone.now()
        customer.save()
        invoice = ensure_invoice(customer)
        self.assertEqual(invoice.contract_terms, customer.delivery_consent)
        self.assertEqual(invoice.line_items[0]['description'], 'Personalised natal chart PDF')

    @override_settings(STRIPE_CHECKOUT_ENABLED=True)
    def test_free_redemption_does_not_require_or_record_paid_terms(self):
        details = dict(DETAILS)
        details.pop('early_delivery_consent')
        self.assertEqual(self.client.post('/redeem-free-natal-chart/', details).status_code, 302)
        self.assertEqual(BirthRequest.objects.get().delivery_consent, {})
        self.assertNotContains(self.client.get('/redeem-free-natal-chart/'), 'name="early_delivery_consent"')

    def test_live_invoice_survives_profile_removal_without_chart_data(self):
        customer = BirthRequest.objects.create(payload={'name': 'Customer', 'birthData': {'city': 'Secret birth city', 'year': 1990}}, email='customer@example.com', status='paid', paid_at=timezone.now(), payment_mode='live', stripe_session_id='cs_live_reference')
        invoice = ensure_invoice(customer, {'name': 'Billing customer', 'address': {'line1': 'Billing address'}})
        number = invoice.number
        removal = DataRemovalRequest.objects.create(birth_request=customer, email=customer.email)
        remove_customer(removal.pk)
        self.assertFalse(BirthRequest.objects.exists())
        invoice.refresh_from_db()
        self.assertIsNone(invoice.birth_request)
        self.assertEqual(invoice.number, number)
        self.assertEqual(invoice.payment_reference, 'cs_live_reference')
        self.assertNotIn('Secret birth city', str(invoice.customer))
        self.assertNotIn('1990', str(invoice.customer))
        self.assertTrue(invoice_pdf(invoice).startswith(b'%PDF'))

    def test_accounting_export_excludes_demo_invoices(self):
        for mode in ['demo', 'live']:
            customer = BirthRequest.objects.create(payload={'name': mode}, email=f'{mode}@example.com', status='paid', paid_at=timezone.now(), payment_mode=mode)
            ensure_invoice(customer)
        self.client.force_login(self.staff)
        response = self.client.post(reverse('admin:studio_invoice_changelist'), {'action': 'export_accounting_invoices', '_selected_action': list(Invoice.objects.values_list('pk', flat=True))})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertContains(response, 'live@example.com')
        self.assertNotContains(response, 'demo@example.com')
        self.assertNotContains(response, 'TEST-')
