from datetime import timedelta
from django.test import TestCase, override_settings
from django.utils import timezone
from .forms import BirthDetailsForm
from .models import BirthRequest
from .test_checkout import DETAILS

class BirthWidgetTests(TestCase):
    def data(self, birth_date='1990-05-15'):
        return {key: value for key, value in {**DETAILS, 'birth_date': birth_date}.items() if key not in {'year', 'month', 'day'}}

    @override_settings(STRIPE_CHECKOUT_ENABLED=False, GOOGLE_MAPS_BROWSER_API_KEY='')
    def test_calendar_on_both_forms_and_exact_payload(self):
        for endpoint in ['/natal-chart/', '/redeem-free-natal-chart/']:
            response = self.client.get(endpoint)
            self.assertContains(response, 'type="date"')
            self.assertContains(response, f'max="{timezone.localdate().isoformat()}"')
            self.assertNotContains(response, 'name="year"')
            self.assertNotContains(response, 'google-places-config')
            self.assertEqual(self.client.post(endpoint, self.data()).status_code, 302)
        for request in BirthRequest.objects.all():
            birthday = request.payload['birthData']
            self.assertEqual((birthday['year'], birthday['month'], birthday['day']), (1990, 5, 15))
            self.assertEqual((birthday['hour'], birthday['minute'], birthday['second']), (12, 0, 0))

    def test_invalid_future_and_empty_calendar_dates(self):
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        for date in ['1990-02-31', tomorrow, '']:
            self.assertFalse(BirthDetailsForm(self.data(date)).is_valid())

    @override_settings(GOOGLE_MAPS_BROWSER_API_KEY='browser-test-key')
    def test_search_config_on_both_forms(self):
        for endpoint in ['/natal-chart/', '/redeem-free-natal-chart/']:
            response = self.client.get(endpoint)
            self.assertContains(response, 'google-places-config')
            self.assertContains(response, 'studio/places.js')
            self.assertContains(response, 'id="id_city"')
            self.assertContains(response, 'id="id_countryCode"')
