from datetime import timedelta
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .forms import BirthDetailsForm
from .models import BirthRequest
from .test_checkout import DETAILS

class SharedBirthValidationTests(TestCase):
    def test_today_allowed_and_tomorrow_rejected_on_both_endpoints(self):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        for endpoint in ['/natal-chart/', '/redeem-free-natal-chart/']:
            with self.subTest(endpoint=endpoint), override_settings(STRIPE_CHECKOUT_ENABLED=False):
                invalid = {**DETAILS, 'year': tomorrow.year, 'month': tomorrow.month, 'day': tomorrow.day}
                self.assertContains(self.client.post(endpoint, invalid), 'Birth date cannot be in the future')
                self.assertFalse(BirthRequest.objects.exists())
                valid = {**DETAILS, 'year': today.year, 'month': today.month, 'day': today.day}
                self.assertEqual(self.client.post(endpoint, valid).status_code, 302)
                BirthRequest.objects.all().delete()

    def test_missing_and_invalid_email_rejected_everywhere(self):
        for endpoint in ['/natal-chart/', '/redeem-free-natal-chart/']:
            for email in ['', 'not-an-email']:
                self.assertEqual(self.client.post(endpoint, {**DETAILS, 'email': email}).status_code, 200)
                self.assertFalse(BirthRequest.objects.exists())

    def test_optional_seconds_and_midnight(self):
        form = BirthDetailsForm({**DETAILS, 'hour': 0, 'minute': 0, 'second': 15})
        self.assertTrue(form.is_valid())
        self.assertEqual({key: form.payload()['birthData'][key] for key in ['hour', 'minute', 'second']}, {'hour': 0, 'minute': 0, 'second': 15})
        self.assertFalse(BirthDetailsForm({**DETAILS, 'second': 60}).is_valid())

class FreeRedemptionTests(TestCase):
    @override_settings(STRIPE_CHECKOUT_ENABLED=True)
    @patch('studio.views.create_checkout')
    def test_free_redemption_saved_and_never_charged(self, checkout):
        self.assertContains(self.client.get('/redeem-free-natal-chart/'), 'Redeem my free natal chart')
        response = self.client.post('/redeem-free-natal-chart/', DETAILS)
        redemption = BirthRequest.objects.get()
        self.assertEqual(redemption.source, 'promotion')
        self.assertEqual(redemption.status, 'free')
        self.assertEqual(redemption.email, 'emma@example.com')
        self.assertEqual(redemption.amount_pence, 0)
        self.assertIsNone(redemption.stripe_session_id)
        self.assertFalse(redemption.report_sent)
        self.assertEqual(redemption.payload['birthData']['hour'], 12)
        self.assertEqual(redemption.payload['birthData']['minute'], 0)
        self.assertEqual(redemption.payload['birthData']['second'], 0)
        self.assertNotIn('email', redemption.payload)
        self.assertRedirects(response, reverse('birth-status', args=[redemption.id]))
        self.assertContains(self.client.get(response.url), 'emma@example.com')
        self.client.get(response.url)
        self.assertEqual(BirthRequest.objects.count(), 1)
        checkout.assert_not_called()
        self.assertEqual(Client().get(response.url).status_code, 404)

    def test_redemption_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post('/redeem-free-natal-chart/', DETAILS).status_code, 403)
        self.assertFalse(BirthRequest.objects.exists())

    @override_settings(STRIPE_CHECKOUT_ENABLED=False)
    def test_storefront_also_saves_delivery_email(self):
        self.client.post('/natal-chart/', DETAILS)
        request = BirthRequest.objects.get()
        self.assertEqual(request.email, DETAILS['email'])
        self.assertEqual(request.source, 'storefront')
        self.assertEqual(request.status, 'submitted')

    def test_admin_can_find_request_and_mark_manually_sent(self):
        self.client.post('/redeem-free-natal-chart/', DETAILS)
        redemption = BirthRequest.objects.get()
        admin = get_user_model().objects.create_superuser('admin-test', 'admin@example.com', 'test-password')
        self.client.force_login(admin)
        listing = reverse('admin:studio_birthrequest_changelist')
        self.assertContains(self.client.get(listing + '?source__exact=promotion&q=Emma'), 'emma@example.com')
        self.assertContains(self.client.get(listing), 'Report sent')
        change = reverse('admin:studio_birthrequest_change', args=[redemption.id])
        self.assertContains(self.client.get(change), 'London')
        response = self.client.post(change, {'report_sent': 'on', '_save': 'Save'})
        self.assertEqual(response.status_code, 302)
        redemption.refresh_from_db()
        self.assertTrue(redemption.report_sent)
        self.assertEqual(redemption.email, DETAILS["email"])
