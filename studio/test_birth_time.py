from django.test import TestCase, override_settings
from .forms import BirthDetailsForm
from .test_checkout import DETAILS

class BirthTimeTests(TestCase):
    def test_single_time_picker_preserves_midnight_and_seconds(self):
        for time, expected in [('00:00', (0, 0, 0)), ('14:30', (14, 30, 0)), ('14:30:15', (14, 30, 15)), ('', (12, 0, 0))]:
            form = BirthDetailsForm({**DETAILS, 'birth_time': time})
            self.assertTrue(form.is_valid(), form.errors)
            data = form.payload()['birthData']
            self.assertEqual((data['hour'], data['minute'], data['second']), expected)

    def test_unknown_time_overrides_previous_time(self):
        form = BirthDetailsForm({**DETAILS, 'birth_time': '14:30', 'unknown_birth_time': 'on'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.payload()['birthData']['hour'], 12)
        self.assertEqual(form.payload()['birthData']['minute'], 0)
        self.assertFalse(BirthDetailsForm({**DETAILS, 'birth_time': '25:61'}).is_valid())

    @override_settings(GOOGLE_MAPS_BROWSER_API_KEY='browser-test-key')
    def test_location_and_time_parts_are_internal(self):
        for url in ['/natal-chart/', '/redeem-free-natal-chart/']:
            response = self.client.get(url)
            self.assertContains(response, 'type="time"')
            for field in ['city', 'countryCode', 'hour', 'minute', 'second']:
                self.assertContains(response, f'type="hidden" name="{field}"')
                self.assertNotContains(response, f'<label for="id_{field}">')
            self.assertContains(response, 'Birth town or city')
