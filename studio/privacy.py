from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.contenttypes.models import ContentType
from django.contrib.sessions.models import Session
from django.db import transaction
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import BirthRequest, ChartEmail, Report, Enquiry, Review, Feedback, DataRemovalRequest, Invoice


@never_cache
@require_http_methods(['GET', 'POST'])
def request_removal(request, token):
    customer = BirthRequest.objects.filter(removal_token=token).first()
    if not customer:
        raise Http404('This removal link is no longer available.')
    pending = DataRemovalRequest.objects.filter(email__iexact=customer.email, approved_at__isnull=True).exists()
    if request.method == 'POST':
        with transaction.atomic():
            customer = BirthRequest.objects.select_for_update().get(pk=customer.pk)
            DataRemovalRequest.objects.get_or_create(birth_request=customer, approved_at=None, defaults={'email': customer.email})
        pending = True
    response = render(request, 'studio/data_removal.html', {'requested': pending})
    response['Referrer-Policy'] = 'same-origin'
    return response


def remove_customer(removal_id):
    """Erase application-owned records after explicit admin approval.

    Leave only a completion timestamp and random audit ID, with no identity.
    Files are removed before DB records so a file error keeps the request pending.
    """
    with transaction.atomic():
        removal = DataRemovalRequest.objects.select_for_update().get(pk=removal_id)
        if removal.approved_at:
            return False
        if not removal.email:
            raise ValueError('This removal request has no email address.')
        customers = list(BirthRequest.objects.select_for_update().filter(email__iexact=removal.email))
        ids = [customer.pk for customer in customers]
        reports = Report.objects.filter(birth_request_id__in=ids)
        emails = ChartEmail.objects.filter(birth_request_id__in=ids)
        invoices = Invoice.objects.filter(birth_request_id__in=ids)
        enquiries = Enquiry.objects.filter(email__iexact=removal.email)
        reviews = Review.objects.filter(birth_request_id__in=ids)
        feedback = Feedback.objects.filter(birth_request_id__in=ids)
        removals = DataRemovalRequest.objects.filter(email__iexact=removal.email)
        # Clear admin history containing customer names, email addresses or changes.
        for queryset in [reports, emails, invoices, enquiries, reviews, feedback, removals, BirthRequest.objects.filter(pk__in=ids)]:
            content_type = ContentType.objects.get_for_model(queryset.model)
            LogEntry.objects.filter(content_type=content_type, object_id__in=[str(pk) for pk in queryset.values_list('pk', flat=True)]).delete()
        for report_id in reports.values_list('pk', flat=True):
            (settings.PRIVATE_REPORT_ROOT / f'{report_id}.pdf').unlink(missing_ok=True)
        customer_ids = {str(pk) for pk in ids}
        for session in Session.objects.all().iterator():
            data = session.get_decoded()
            owned = data.get('birth_requests', [])
            if customer_ids.intersection(owned) or data.get('active_birth_request') in customer_ids:
                data['birth_requests'] = [pk for pk in owned if pk not in customer_ids]
                if data.get('active_birth_request') in customer_ids:
                    data.pop('active_birth_request', None)
                session.session_data = Session.objects.encode(data)
                session.save(update_fields=['session_data'])
        invoices.filter(is_test=True).delete()
        emails.delete()  # These protect their PDF/request until explicitly erased.
        reports.delete()
        enquiries.delete()
        reviews.delete()
        feedback.delete()
        BirthRequest.objects.filter(pk__in=ids).delete()
        removals.update(email='', birth_request=None, approved_at=timezone.now())
        return True
