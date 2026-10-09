import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import patch
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from .forms import BirthDetailsForm, ReportForm
from .models import BirthRequest
from .payments import create_checkout

DETAILS = {'early_delivery_consent': 'on', 'email': 'emma@example.com', 'name': 'Emma Johnson', 'year': 1990, 'month': 5, 'day': 15, 'city': 'London', 'countryCode': 'GB'}

class BirthFormTests(TestCase):
    def test_defaults_and_exact_payload(self):
        form = BirthDetailsForm(DETAILS)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.payload(), {'name': 'Emma Johnson', 'birthData': {'year': 1990, 'month': 5, 'day': 15, 'hour': 12, 'minute': 0, 'second': 0, 'city': 'London', 'countryCode': 'GB'}})

    def test_midnight_and_supplied_time_preserved(self):
        for hour, minute in [(0, 0), (14, 30)]:
            form = BirthDetailsForm({**DETAILS, 'hour': hour, 'minute': minute, 'countryCode': 'gb'})
            self.assertTrue(form.is_valid())
            self.assertEqual(form.payload()['birthData']['hour'], hour)
            self.assertEqual(form.payload()['birthData']['minute'], minute)
            self.assertEqual(form.payload()['birthData']['countryCode'], 'GB')

    def test_invalid_details(self):
        for override in [{'day': 31, 'month': 2}, {'hour': 24}, {'minute': 60}, {'city': ''}, {'countryCode': ''}, {'countryCode': 'UKK'}, {'name': ''}, {'year': 9999}]:
            self.assertFalse(BirthDetailsForm({**DETAILS, **override}).is_valid(), override)

    def test_text_files_and_pasted_admin_data(self):
        chart = (settings.BASE_DIR / 'source_files/natal_chart.json').read_text()
        svg = (settings.BASE_DIR / 'source_files/chart_render.svg').read_text()
        self.assertTrue(ReportForm({'json_text': chart, 'svg_text': svg}).is_valid())
        files = {'chart_json': SimpleUploadedFile('chart.txt', chart.encode()), 'chart_svg': SimpleUploadedFile('wheel.txt', svg.encode())}
        self.assertTrue(ReportForm(files=files).is_valid())
        files['chart_json'].seek(0)
        files['chart_svg'].seek(0)
        self.assertFalse(ReportForm({'json_text': chart}, files=files).is_valid())

@override_settings(STRIPE_CHECKOUT_ENABLED=False)
class DisabledCheckoutTests(TestCase):
    @patch('studio.views.create_checkout')
    def test_disabled_never_contacts_stripe_or_marks_paid(self, checkout):
        response = self.client.post('/natal-chart/', DETAILS)
        order = BirthRequest.objects.get()
        self.assertEqual(order.status, BirthRequest.Status.SUBMITTED)
        self.assertIsNone(order.stripe_session_id)
        self.assertRedirects(response, reverse('birth-status', args=[order.id]))
        checkout.assert_not_called()
        self.assertContains(self.client.get('/natal-chart/'), 'Payments are currently disabled')

    def test_invalid_does_not_create_request(self):
        self.client.post('/natal-chart/', {**DETAILS, 'day': 99})
        self.assertFalse(BirthRequest.objects.exists())

    def test_status_is_private(self):
        self.client.post('/natal-chart/', DETAILS)
        order = BirthRequest.objects.get()
        from django.test import Client
        self.assertEqual(Client().get(reverse('birth-status', args=[order.id])).status_code, 404)

@override_settings(PAYMENT_MODE='test', STRIPE_CHECKOUT_ENABLED=True, STRIPE_SECRET_KEY='sk_test_placeholder', STRIPE_WEBHOOK_SECRET='whsec_test', PUBLIC_BASE_URL='https://example.com')
class EnabledCheckoutTests(TestCase):
    @patch('studio.payments.stripe.StripeClient')
    def test_price_reference_and_no_birth_data_sent_to_stripe(self, client):
        order = BirthRequest.objects.create(payload={'name': 'Emma Johnson', 'birthData': {'city': 'London'}}, status='pending')
        create_checkout(order)
        args, kwargs = client.return_value.v1.checkout.sessions.create.call_args
        data = args[0]
        self.assertEqual(data['line_items'][0]['price_data']['unit_amount'], 3900)
        self.assertEqual(data['line_items'][0]['price_data']['currency'], 'gbp')
        self.assertEqual(data['metadata'], {'birth_request_id': str(order.id)})
        self.assertNotIn('Emma Johnson', json.dumps(data))
        self.assertNotIn('London', json.dumps(data))
        self.assertEqual(kwargs['options']['idempotency_key'], f'birth-request-{order.id}-initial')

    @patch('studio.payments.stripe.StripeClient')
    def test_existing_checkout_is_reused_or_replaced_when_expired(self, client):
        from .payments import CheckoutAlreadyCompleted
        order = BirthRequest.objects.create(payload={'name': 'Test'}, status='pending', stripe_session_id='cs_old')
        sessions = client.return_value.v1.checkout.sessions
        sessions.retrieve.return_value = SimpleNamespace(id='cs_old', status='open', url='https://checkout.stripe.com/test')
        self.assertEqual(create_checkout(order).id, 'cs_old')
        sessions.create.assert_not_called()
        sessions.retrieve.return_value = SimpleNamespace(id='cs_old', status='complete')
        with self.assertRaises(CheckoutAlreadyCompleted):
            create_checkout(order)
        sessions.retrieve.return_value = SimpleNamespace(id='cs_old', status='expired')
        create_checkout(order)
        self.assertEqual(sessions.create.call_args.kwargs['options']['idempotency_key'], f'birth-request-{order.id}-cs_old')

    @patch('studio.views.create_checkout', return_value=SimpleNamespace(id='cs_test_order', url='https://checkout.stripe.com/test'))
    def test_checkout_redirect_and_retry_reuses_order(self, checkout):
        response = self.client.post('/natal-chart/', DETAILS)
        self.assertEqual(response.url, 'https://checkout.stripe.com/test')
        order = BirthRequest.objects.get()
        self.assertEqual(order.status, 'pending')
        self.assertEqual(order.stripe_session_id, 'cs_test_order')
        self.client.post('/natal-chart/', DETAILS)
        self.assertEqual(BirthRequest.objects.count(), 1)
        self.assertContains(self.client.get(reverse('birth-status', args=[order.id])), 'Awaiting payment confirmation')
        order.refresh_from_db()
        self.assertIsNone(order.paid_at)

    @override_settings(STRIPE_SECRET_KEY='')
    @patch('studio.views.create_checkout')
    def test_missing_credentials_fail_closed(self, checkout):
        self.assertContains(self.client.post('/natal-chart/', DETAILS), 'temporarily unavailable')
        checkout.assert_not_called()
        self.assertFalse(BirthRequest.objects.exists())

    @patch('studio.views.create_checkout')
    def test_checkout_provider_failure_is_recoverable(self, checkout):
        import stripe
        checkout.side_effect = stripe.APIConnectionError('Network unavailable')
        with self.assertLogs('studio.views', level='WARNING'):
            response = self.client.post('/natal-chart/', DETAILS)
        self.assertContains(response, 'could not open checkout')
        self.assertEqual(BirthRequest.objects.get().status, 'pending')

@override_settings(STRIPE_WEBHOOK_SECRET='whsec_test', STRIPE_CHECKOUT_ENABLED=False)
class WebhookTests(TestCase):
    def setUp(self):
        self.order = BirthRequest.objects.create(payload={'name': 'Test'}, status='pending', stripe_session_id='cs_test_order')

    def event(self, **changes):
        checkout = {'id': 'cs_test_order', 'metadata': {'birth_request_id': str(self.order.id)}, 'client_reference_id': str(self.order.id), 'payment_status': 'paid', 'amount_total': 3900, 'currency': 'gbp', 'mode': 'payment', 'customer_details': {'email': 'test@example.com'}}
        checkout.update(changes)
        return {'id': 'evt_test', 'object': 'event', 'type': 'checkout.session.completed', 'data': {'object': checkout}}

    def post_event(self, event, secret='whsec_test'):
        body = json.dumps(event)
        timestamp = int(time.time())
        signature = hmac.new(secret.encode(), f'{timestamp}.{body}'.encode(), hashlib.sha256).hexdigest()
        return self.client.post('/stripe/webhook/', body, content_type='application/json', HTTP_STRIPE_SIGNATURE=f't={timestamp},v1={signature}')

    def test_valid_payment_and_repeated_delivery_with_flag_off(self):
        self.assertEqual(self.post_event(self.event()).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertEqual(self.order.email, 'test@example.com')
        paid_at = self.order.paid_at
        self.post_event(self.event())
        self.order.refresh_from_db()
        self.assertEqual(self.order.paid_at, paid_at)

    def test_bad_signature_rejected(self):
        self.assertEqual(self.post_event(self.event(), secret='wrong').status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_amount_currency_session_and_reference_must_match(self):
        for changes in [{'amount_total': 1}, {'currency': 'usd'}, {'id': 'cs_other'}, {'client_reference_id': 'wrong'}, {'mode': 'subscription'}]:
            self.assertEqual(self.post_event(self.event(**changes)).status_code, 400)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')

    def test_unpaid_session_and_unrelated_events_ignored(self):
        self.assertEqual(self.post_event(self.event(payment_status='unpaid')).status_code, 200)
        event = self.event()
        event['type'] = 'payment_intent.created'
        self.assertEqual(self.post_event(event).status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'pending')
