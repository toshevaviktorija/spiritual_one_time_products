import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings, Client
from django.urls import reverse
from .models import BirthRequest, Report, ChartEmail
from .forms import BirthDetailsForm, EnquiryForm
from .emailing import ChartEmailError
from .test_checkout import DETAILS


@override_settings(RESEND_API_KEY='test-key', RESEND_FROM_EMAIL='charts@example.com', RESEND_REPLY_TO='hello@example.com', PUBLIC_BASE_URL='https://venastella.com')
class AdminWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('chart-admin', 'admin@example.com', 'test-password')
        self.client.force_login(self.user)
        self.request = BirthRequest.objects.create(payload={'name': 'Emma'}, email='emma@example.com')
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(PRIVATE_REPORT_ROOT=Path(self.directory.name))
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.report = Report.objects.create(name='Emma', birth_request=self.request, created_by=self.user)
        self.content = b'%PDF-test-personal-chart'
        self.file = Path(self.directory.name) / f'{self.report.pk}.pdf'
        self.file.write_bytes(self.content)
        self.compose_url = reverse('admin:studio_birthrequest_email', args=[self.request.pk])

    def draft(self):
        response = self.client.post(self.compose_url, {'report': str(self.report.pk), 'subject': 'Your stars', 'message': 'Hello <script>secret</script>\nYour chart is ready.'})
        self.assertEqual(response.status_code, 302)
        return ChartEmail.objects.latest('created_at')

    def test_permission_and_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.get(self.compose_url).status_code, 302)
        client.force_login(self.user)
        self.assertEqual(client.post(self.compose_url, {}).status_code, 403)
        staff = get_user_model().objects.create_user('limited', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(self.compose_url).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:studio_report_generate')).status_code, 403)

    def test_generate_associates_pdf_and_downloads(self):
        uploads = {'chart_json': SimpleUploadedFile('chart.txt', (settings.BASE_DIR / 'source_files/natal_chart.json').read_bytes()),
                   'chart_svg': SimpleUploadedFile('chart.txt', (settings.BASE_DIR / 'source_files/chart_render.svg').read_bytes())}
        def renderer(chart_json, chart_svg, destination):
            destination.write_bytes(b'%PDF-generated')
        with patch('studio.admin_workflow.generate_report', side_effect=renderer):
            response = self.client.post(reverse('admin:studio_report_generate') + '?request=' + str(self.request.pk), uploads)
        self.assertEqual(response.status_code, 302)
        report = Report.objects.exclude(pk=self.report.pk).get()
        self.assertEqual(report.birth_request, self.request)
        download = self.client.get(reverse('admin:studio_report_download', args=[report.pk]))
        self.assertEqual(b''.join(download.streaming_content), b'%PDF-generated')

    def test_preview_does_not_send_and_escapes_message(self):
        with patch('studio.emailing.urlopen') as transport:
            draft = self.draft()
            response = self.client.get(reverse('admin:studio_chartemail_preview', args=[draft.pk]))
            self.assertContains(response, 'emma@example.com')
            self.assertContains(response, 'Download PDF to inspect')
            self.assertNotContains(response, '<script>secret</script>')
            transport.assert_not_called()
        self.request.refresh_from_db()
        self.assertFalse(self.request.report_sent)

    def test_inspection_required_and_success_is_idempotent(self):
        draft = self.draft()
        url = reverse('admin:studio_chartemail_preview', args=[draft.pk])
        transport_response = MagicMock()
        transport_response.__enter__.return_value.read.return_value = b'{"id":"provider-test"}'
        with patch('studio.emailing.urlopen', return_value=transport_response) as transport:
            self.assertEqual(self.client.post(url, {}).status_code, 200)
            transport.assert_not_called()
            self.assertEqual(self.client.post(url, {'inspected': 'on'}).status_code, 302)
            api_request = transport.call_args.args[0]
            payload = json.loads(api_request.data)
            self.assertEqual(payload['to'], ['emma@example.com'])
            self.assertEqual(base64.b64decode(payload['attachments'][0]['content']), self.content)
            self.assertEqual(payload['reply_to'], 'hello@example.com')
            self.assertIn('Venastella', payload['html'])
            self.assertIn('https://venastella.com/reviews/', payload['text'])
            self.assertIn('href="https://venastella.com/reviews/"', payload['html'])
            self.assertIn('Share your review', payload['html'])
            self.assertEqual(self.client.post(url, {'inspected': 'on'}).status_code, 302)
            self.assertEqual(transport.call_count, 1)
        self.request.refresh_from_db()
        self.assertTrue(self.request.report_sent)
        draft.refresh_from_db()
        self.assertEqual(draft.provider_id, 'provider-test')
        self.assertFalse(self.file.exists())
        self.assertEqual(draft.message, '')
        self.assertIn('/data-removal/', payload['html'])
        self.assertIn('/data-removal/', payload['text'])

    def test_failed_send_keeps_unsent_state(self):
        draft = self.draft()
        with patch('studio.admin_workflow.submit_email', side_effect=ChartEmailError('Provider unavailable')):
            response = self.client.post(reverse('admin:studio_chartemail_preview', args=[draft.pk]), {'inspected': 'on'})
        self.assertContains(response, 'Provider unavailable')
        draft.refresh_from_db()
        self.assertIsNone(draft.submitted_at)
        self.request.refresh_from_db()
        self.assertFalse(self.request.report_sent)

    def test_attachment_is_limited_to_customer_and_immutable(self):
        other = BirthRequest.objects.create(payload={'name': 'Other'}, email='other@example.com')
        other_report = Report.objects.create(name='Other', birth_request=other, created_by=self.user)
        response = self.client.post(self.compose_url, {'report': str(other_report.pk), 'subject': 'Test', 'message': 'Test'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ChartEmail.objects.exists())
        draft = self.draft()
        self.file.write_bytes(b'%PDF-changed')
        with patch('studio.emailing.urlopen') as transport:
            response = self.client.post(reverse('admin:studio_chartemail_preview', args=[draft.pk]), {'inspected': 'on'})
            self.assertContains(response, 'PDF changed')
            transport.assert_not_called()

    def test_incomplete_email_rejected(self):
        for address in ['a@a', 'a@localhost', 'a@bad_domain.com', 'a@.com', 'a@@example.com']:
            self.assertFalse(BirthDetailsForm({**DETAILS, 'email': address}).is_valid(), address)
            self.assertFalse(EnquiryForm({'name': 'Emma', 'email': address}).is_valid(), address)
        self.assertTrue(BirthDetailsForm({**DETAILS, 'email': 'emma+chart@example.co.uk'}).is_valid())

    def test_paid_delivery_attaches_chart_and_invoice(self):
        from .invoicing import ensure_invoice
        from django.utils import timezone
        self.request.status = 'paid'
        self.request.payment_mode = 'test'
        self.request.paid_at = timezone.now()
        self.request.save()
        invoice = ensure_invoice(self.request)
        draft = self.draft()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"id":"test-paid-email"}'
        with patch('studio.emailing.urlopen', return_value=response) as transport:
            self.assertEqual(self.client.post(reverse('admin:studio_chartemail_preview', args=[draft.pk]), {'inspected': 'on'}).status_code, 302)
        payload = json.loads(transport.call_args.args[0].data)
        self.assertEqual(len(payload['attachments']), 2)
        self.assertIn(invoice.number, payload['attachments'][1]['filename'])
        self.assertTrue(base64.b64decode(payload['attachments'][1]['content']).startswith(b'%PDF'))
        self.assertIn('Thank you for your business', payload['html'])
        self.assertIn('Request removal of my data', payload['html'])
        self.assertIn('TEST PAYMENT', payload['subject'])
