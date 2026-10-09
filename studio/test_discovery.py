from xml.etree import ElementTree
import re
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from .forms import ReviewForm


@override_settings(PUBLIC_BASE_URL='https://example.com')
class DiscoveryTests(TestCase):
    def test_sitemap_only_contains_public_pages(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        root = ElementTree.fromstring(response.content)
        urls = [node.text for node in root.findall('.//{*}loc')]
        self.assertEqual(set(urls), {'https://example.com/', 'https://example.com/natal-chart/', 'https://example.com/redeem-free-natal-chart/', 'https://example.com/reviews/'})

    def test_robots_announces_sitemap_without_private_paths(self):
        response = self.client.get('/robots.txt')
        self.assertContains(response, 'Sitemap: https://example.com/sitemap.xml')
        self.assertNotContains(response, '/studio/')
        self.assertNotContains(response, '/admin/')

    def test_private_routes_are_noindex_and_still_require_login(self):
        for path in ['/studio/', '/admin/', '/orders/00000000-0000-0000-0000-000000000000/', '/natal-chart/thanks/']:
            self.assertEqual(self.client.get(path)['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(self.client.get('/studio/').status_code, 302)
        self.assertNotIn('X-Robots-Tag', self.client.get('/reviews/'))

    def test_studio_links_absent_even_for_staff(self):
        user = get_user_model().objects.create_user('staff', is_staff=True)
        self.client.force_login(user)
        for path in ['/', '/reviews/', '/natal-chart/', '/redeem-free-natal-chart/']:
            self.assertNotContains(self.client.get(path), 'href="/studio/"')

    def test_default_rating_and_explicit_selection(self):
        self.assertEqual(ReviewForm()['rating'].value(), 5)
        response = self.client.get('/reviews/')
        radio = re.search(r'<input[^>]*name="review-rating"[^>]*value="5"[^>]*>', response.content.decode()).group()
        self.assertIn('checked', radio)
        form = ReviewForm({'rating': '3', 'text': 'Lovely chart'})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['rating'], 3)
