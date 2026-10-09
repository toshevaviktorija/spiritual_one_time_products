import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .models import BirthRequest, Report, ChartEmail, DataRemovalRequest, Review, Feedback, Enquiry, Invoice
from .privacy import remove_customer


class PrivacyTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('privacy-admin', 'admin@example.com', 'test-password')
        self.customer = BirthRequest.objects.create(payload={'name': 'Private customer'}, email='person@example.com')
        self.other = BirthRequest.objects.create(payload={'name': 'Other'}, email='other@example.com')
        self.url = reverse('data-removal', args=[self.customer.removal_token])
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings_override = override_settings(PRIVATE_REPORT_ROOT=Path(self.directory.name))
        settings_override.enable()
        self.addCleanup(settings_override.disable)

    def test_link_get_is_safe_post_requires_csrf_and_queues_once(self):
        client = Client(enforce_csrf_checks=True)
        self.assertContains(client.get(self.url), 'Request removal of my data')
        self.assertFalse(DataRemovalRequest.objects.exists())
        self.assertEqual(client.post(self.url).status_code, 403)
        token = client.get('/csrf-token/').json()['token']
        response = client.post(self.url, {'csrfmiddlewaretoken': token})
        self.assertContains(response, 'waiting for approval')
        client.post(self.url, {'csrfmiddlewaretoken': token})
        self.assertEqual(DataRemovalRequest.objects.count(), 1)
        self.assertEqual(BirthRequest.objects.count(), 2)
        self.assertEqual(response['X-Robots-Tag'], 'noindex, nofollow')
        self.assertIn('no-store', response['Cache-Control'])

    def test_approval_erases_linked_data_files_logs_and_session_references(self):
        from .invoicing import ensure_invoice
        self.customer.status = 'paid'
        self.customer.paid_at = timezone.now()
        self.customer.save()
        ensure_invoice(self.customer)
        second = BirthRequest.objects.create(payload={'name': 'Second'}, email='PERSON@example.com')
        removal = DataRemovalRequest.objects.create(birth_request=self.customer, email=self.customer.email)
        report = Report.objects.create(name='Private customer', birth_request=self.customer, created_by=self.admin)
        pdf = Path(self.directory.name) / f'{report.pk}.pdf'
        pdf.write_bytes(b'%PDF-private')
        ChartEmail.objects.create(birth_request=self.customer, report=report, recipient=self.customer.email, sender='info@venastella.com', subject='Private subject', message='Private message', pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), created_by=self.admin)
        Review.objects.create(birth_request=second, rating=5, text='Linked review')
        Feedback.objects.create(birth_request=self.customer, text='Linked feedback')
        anonymous = Review.objects.create(rating=4, text='Unrelated anonymous review')
        Enquiry.objects.create(name='Private customer', email='PERSON@example.com')
        Enquiry.objects.create(name='Other', email='other@example.com')
        LogEntry.objects.create(user=self.admin, content_type=ContentType.objects.get_for_model(BirthRequest), object_id=str(self.customer.pk), object_repr='Private customer', action_flag=CHANGE, change_message='Private address changed')
        session = self.client.session
        session['active_birth_request'] = str(self.customer.pk)
        session['birth_requests'] = [str(self.customer.pk), str(self.other.pk)]
        session.save()
        self.client.force_login(self.admin)
        url = reverse('admin:studio_dataremoval_approve', args=[removal.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(pdf.exists())
        self.assertEqual(self.client.post(url, {'confirm': 'yes'}).status_code, 302)
        self.assertFalse(pdf.exists())
        self.assertEqual(list(BirthRequest.objects.values_list('pk', flat=True)), [self.other.pk])
        self.assertFalse(Invoice.objects.exists())
        self.assertFalse(ChartEmail.objects.exists())
        self.assertFalse(Report.objects.exists())
        self.assertFalse(Feedback.objects.exists())
        self.assertEqual(Review.objects.get(), anonymous)
        self.assertEqual(Enquiry.objects.get().email, 'other@example.com')
        self.assertFalse(LogEntry.objects.filter(object_repr='Private customer').exists())
        removal.refresh_from_db()
        self.assertEqual(removal.email, '')
        self.assertIsNone(removal.birth_request)
        self.assertIsNotNone(removal.approved_at)
        self.assertNotIn('active_birth_request', self.client.session)
        self.assertEqual(self.client.session['birth_requests'], [str(self.other.pk)])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertFalse(remove_customer(removal.pk))
        self.assertTrue(get_user_model().objects.filter(pk=self.admin.pk).exists())

    def test_permission_file_failure_and_missing_confirmation(self):
        removal = DataRemovalRequest.objects.create(birth_request=self.customer, email=self.customer.email)
        report = Report.objects.create(name='Test', birth_request=self.customer, created_by=self.admin)
        url = reverse('admin:studio_dataremoval_approve', args=[removal.pk])
        self.assertEqual(self.client.post(url, {'confirm': 'yes'}).status_code, 302)
        self.assertTrue(BirthRequest.objects.filter(pk=self.customer.pk).exists())
        staff = get_user_model().objects.create_user('limited', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(url, {'confirm': 'yes'}).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(url, {})
        self.assertTrue(BirthRequest.objects.filter(pk=self.customer.pk).exists())
        with patch('pathlib.Path.unlink', side_effect=PermissionError):
            response = self.client.post(url, {'confirm': 'yes'})
        self.assertContains(response, 'remains pending')
        removal.refresh_from_db()
        self.assertIsNone(removal.approved_at)
        self.assertTrue(Report.objects.filter(pk=report.pk).exists())

    def test_confirmed_delivery_blocks_if_removal_pending(self):
        from .emailing import submit_email, ChartEmailError
        report = Report.objects.create(name='Test', birth_request=self.customer, created_by=self.admin)
        draft = ChartEmail.objects.create(birth_request=self.customer, report=report, recipient=self.customer.email, sender='info@venastella.com', subject='Chart', message='Hello', created_by=self.admin)
        DataRemovalRequest.objects.create(birth_request=self.customer, email=self.customer.email)
        with override_settings(RESEND_API_KEY='test'), patch('studio.emailing.urlopen') as transport:
            with self.assertRaisesMessage(ChartEmailError, 'requested data removal'):
                submit_email(draft)
            transport.assert_not_called()
