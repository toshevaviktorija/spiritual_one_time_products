import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from pypdf import PdfReader
from .forms import ReportForm
from .models import Enquiry, Report
from .services import generate_report

class WebsiteTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user('studio', password='test-password', is_staff=True)

    def uploads(self):
        return {
            'chart_json': SimpleUploadedFile('chart.json', (settings.BASE_DIR / 'source_files/natal_chart.json').read_bytes()),
            'chart_svg': SimpleUploadedFile('chart.svg', (settings.BASE_DIR / 'source_files/chart_render.svg').read_bytes()),
        }

    def test_storefront_and_enquiry(self):
        self.assertContains(self.client.get('/'), 'VENASTELLA')
        self.assertContains(self.client.get('/enquiries/'), 'does not place an order')
        response = self.client.post('/enquiries/', {'name': 'Test Person', 'email': 'test@example.com', 'message': 'Interested'})
        self.assertRedirects(response, reverse('enquiry-thanks'))
        self.assertEqual(Enquiry.objects.count(), 1)

    def test_invalid_enquiry_is_not_saved(self):
        self.client.post('/enquiries/', {'name': 'Test', 'email': 'invalid'})
        self.assertFalse(Enquiry.objects.exists())

    def test_private_routes_require_staff(self):
        report = Report.objects.create(name='Private Name', created_by=self.staff)
        url = reverse('report-download', args=[report.id])
        for user in (None, get_user_model().objects.create_user('customer', password='test-password')):
            if user:
                self.client.force_login(user)
            self.assertEqual(self.client.get('/studio/').status_code, 302)
            self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(self.client.get('/private_reports/' + str(report.id) + '.pdf').status_code, 404)

    def test_download_and_staff_dashboard(self):
        self.client.force_login(self.staff)
        report = Report.objects.create(name='Test', created_by=self.staff)
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_REPORT_ROOT=Path(directory)):
            self.assertContains(self.client.get('/studio/'), 'Test')
            url = reverse('report-download', args=[report.id])
            self.assertEqual(self.client.get(url).status_code, 404)
            (Path(directory) / f'{report.id}.pdf').write_bytes(b'%PDF-test')
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            self.assertEqual(b''.join(response.streaming_content), b'%PDF-test')

    def test_existing_input_passes_validation(self):
        self.assertTrue(ReportForm(files=self.uploads()).is_valid())

    def test_untrusted_svg_rejected(self):
        for svg in [b'<!DOCTYPE svg><svg xmlns="http://www.w3.org/2000/svg"/>', b'<svg xmlns="http://www.w3.org/2000/svg"><use href="file:///etc/passwd"/></svg>', b'<svg xmlns="http://www.w3.org/2000/svg"><style>@import "https://example.com";</style></svg>']:
            uploads = self.uploads()
            uploads['chart_svg'] = SimpleUploadedFile('bad.svg', svg)
            form = ReportForm(files=uploads)
            self.assertFalse(form.is_valid())
            self.assertIn('chart_svg', form.errors)

    def test_malformed_json_rejected(self):
        uploads = self.uploads()
        uploads['chart_json'] = SimpleUploadedFile('bad.json', b'[]')
        form = ReportForm(files=uploads)
        self.assertFalse(form.is_valid())
        self.assertIn('chart_json', form.errors)

    @patch('studio.views.generate_report', side_effect=subprocess.TimeoutExpired('renderer', 120))
    def test_failed_generation_leaves_no_record(self, renderer):
        self.client.force_login(self.staff)
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_REPORT_ROOT=Path(directory)):
            with self.assertLogs('studio.views', level='ERROR'):
                response = self.client.post('/studio/', self.uploads())
            self.assertContains(response, 'could not generate')
            self.assertFalse(Report.objects.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_real_pdf_generation_through_studio(self):
        self.client.force_login(self.staff)
        with tempfile.TemporaryDirectory() as directory, override_settings(PRIVATE_REPORT_ROOT=Path(directory)):
            response = self.client.post('/studio/', self.uploads())
            self.assertRedirects(response, reverse('studio'))
            report = Report.objects.get()
            pdf = PdfReader(Path(directory) / f'{report.id}.pdf')
            self.assertGreater(len(pdf.pages), 10)
            self.assertIn('NATAL CHART', pdf.pages[0].extract_text().upper())
            legacy_path = Path(directory) / 'legacy.pdf'
            subprocess.run([sys.executable, 'scripts/natal_chart/generate_natal_chart.py', str(settings.BASE_DIR / 'source_files/natal_chart.json'), str(legacy_path)], cwd=settings.BASE_DIR, check=True, capture_output=True, timeout=120)
            legacy = PdfReader(legacy_path)
            self.assertEqual([page.extract_text() for page in pdf.pages], [page.extract_text() for page in legacy.pages])

    def test_palette_matches_existing_theme(self):
        self.assertContains(self.client.get('/brand.css'), '--background:#100820', status_code=200)
