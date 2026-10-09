import re
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from .models import BirthRequest
from .test_checkout import DETAILS


@override_settings(STRIPE_CHECKOUT_ENABLED=False)
class CsrfTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    def test_login_rotation_then_refresh_allows_redemption(self):
        get_user_model().objects.create_superuser('csrf-admin', 'admin@example.com', 'test-password')
        page = self.client.get('/redeem-free-natal-chart/')
        old = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page.content.decode()).group(1)
        login = self.client.post('/admin/login/?next=/admin/', {'username': 'csrf-admin', 'password': 'test-password', 'csrfmiddlewaretoken': old, 'next': '/admin/'})
        self.assertEqual(login.status_code, 302)
        rejected = self.client.post('/redeem-free-natal-chart/', {**DETAILS, 'csrfmiddlewaretoken': old})
        self.assertContains(rejected, 'Your form needs a fresh start.', status_code=403)
        self.assertFalse(BirthRequest.objects.exists())
        fresh = self.client.get('/csrf-token/')
        self.assertIn('no-store', fresh['Cache-Control'])
        accepted = self.client.post('/redeem-free-natal-chart/', {**DETAILS, 'csrfmiddlewaretoken': fresh.json()['token']})
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(BirthRequest.objects.get().status, 'free')

    def test_missing_token_and_foreign_origin_still_rejected(self):
        self.assertEqual(self.client.post('/redeem-free-natal-chart/', DETAILS).status_code, 403)
        token = self.client.get('/csrf-token/').json()['token']
        self.assertEqual(self.client.post('/redeem-free-natal-chart/', {**DETAILS, 'csrfmiddlewaretoken': token}, HTTP_ORIGIN='https://untrusted.example').status_code, 403)
        self.assertFalse(BirthRequest.objects.exists())

    def test_refresh_does_not_create_requests_and_is_get_only(self):
        response = self.client.get('/csrf-token/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertNotIn('Access-Control-Allow-Origin', response)
        self.assertFalse(BirthRequest.objects.exists())
        token = response.json()['token']
        self.assertEqual(self.client.post('/csrf-token/', {'csrfmiddlewaretoken': token}).status_code, 405)

    def test_public_forms_are_not_cached(self):
        for path in ['/natal-chart/', '/redeem-free-natal-chart/', '/reviews/', '/enquiries/']:
            response = self.client.get(path)
            self.assertIn('no-store', response['Cache-Control'])
            self.assertContains(response, '/static/studio/csrf.js')
