import hashlib
import subprocess
from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from .forms import ReportForm, ChartEmailForm, InspectEmailForm
from .models import BirthRequest, Report, ChartEmail
from .services import generate_report
from .emailing import ChartEmailError, email_html, pdf_content, submit_email
from .validators import validate_delivery_email


def context(model_admin, request, **extra):
    return {**model_admin.admin_site.each_context(request), 'opts': model_admin.model._meta, **extra}


def require_permission(request, permission):
    if not request.user.has_perm(permission):
        raise PermissionDenied


def generate(model_admin, request):
    require_permission(request, 'studio.add_report')
    birth_request = None
    if request.GET.get('request'):
        birth_request = get_object_or_404(BirthRequest, pk=request.GET['request'])
        require_permission(request, 'studio.change_birthrequest')
    form = ReportForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        report = Report(name=form.chart_data.name[:200], created_by=request.user, birth_request=birth_request)
        destination = settings.PRIVATE_REPORT_ROOT / f'{report.id}.pdf'
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with transaction.atomic():
                if birth_request:
                    get_object_or_404(BirthRequest.objects.select_for_update(), pk=birth_request.pk)
                generate_report(form.cleaned_data['chart_json'], form.cleaned_data['chart_svg'], destination)
                report.save()
        except (subprocess.SubprocessError, OSError):
            destination.unlink(missing_ok=True)
            form.add_error(None, 'Generation failed. Check that the JSON and SVG match and contain complete chart data.')
        else:
            messages.success(request, 'PDF generated. Download it and inspect it before composing an email.')
            return redirect('admin:studio_report_change', report.pk)
    return render(request, 'admin/studio/generate.html', context(model_admin, request, title='Generate natal chart PDF', form=form, birth_request=birth_request))


def download(model_admin, request, report_id):
    require_permission(request, 'studio.view_report')
    report = get_object_or_404(Report, pk=report_id)
    path = settings.PRIVATE_REPORT_ROOT / f'{report.pk}.pdf'
    if not path.is_file():
        raise Http404('PDF unavailable')
    response = FileResponse(path.open('rb'), as_attachment=True, filename='Venastella_Natal_Chart.pdf')
    response['Cache-Control'] = 'private, no-store'
    return response


def compose(model_admin, request, request_id):
    require_permission(request, 'studio.change_birthrequest')
    require_permission(request, 'studio.view_report')
    birth_request = get_object_or_404(BirthRequest, pk=request_id)
    form = ChartEmailForm(request.POST or None, birth_request=birth_request)
    if request.method == 'POST' and form.is_valid():
        try:
            validate_delivery_email(birth_request.email)
            content = pdf_content(form.cleaned_data['report'])
        except (ValidationError, ChartEmailError) as error:
            form.add_error(None, str(error) if isinstance(error, ChartEmailError) else 'The recipient needs a complete email address. Correct it before composing.')
        else:
            draft = ChartEmail.objects.create(birth_request=birth_request, report=form.cleaned_data['report'], recipient=birth_request.email,
                sender=settings.RESEND_FROM_EMAIL, reply_to=settings.RESEND_REPLY_TO, subject=form.cleaned_data['subject'],
                message=form.cleaned_data['message'], pdf_sha256=hashlib.sha256(content).hexdigest(), created_by=request.user)
            return redirect('admin:studio_chartemail_preview', draft.pk)
    return render(request, 'admin/studio/compose.html', context(model_admin, request, title='Compose chart email', form=form, birth_request=birth_request,
        history=birth_request.chart_emails.filter(submitted_at__isnull=False), sender=settings.RESEND_FROM_EMAIL))


def preview(model_admin, request, draft_id):
    require_permission(request, 'studio.change_birthrequest')
    require_permission(request, 'studio.view_report')
    draft = get_object_or_404(ChartEmail.objects.select_related('report', 'birth_request'), pk=draft_id)
    form = InspectEmailForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            BirthRequest.objects.select_for_update().get(pk=draft.birth_request_id)
            draft = ChartEmail.objects.select_for_update().select_related('report', 'birth_request').get(pk=draft_id)
            if draft.submitted_at:
                messages.info(request, 'This email has already been submitted to Resend.')
            else:
                try:
                    provider_id = submit_email(draft)
                except (ChartEmailError, ValidationError) as error:
                    form.add_error(None, str(error) if isinstance(error, ChartEmailError) else 'The sender, recipient or reply address is invalid.')
                else:
                    draft.provider_id = provider_id
                    draft.submitted_at = timezone.now()
                    draft.message = ''
                    draft.subject = 'Natal chart delivery'
                    draft.pdf_sha256 = ''
                    draft.save(update_fields=['provider_id', 'submitted_at', 'message', 'subject', 'pdf_sha256'])
                    BirthRequest.objects.filter(pk=draft.birth_request_id).update(report_sent=True)
                    try:
                        (settings.PRIVATE_REPORT_ROOT / f'{draft.report_id}.pdf').unlink(missing_ok=True)
                    except OSError:
                        messages.error(request, 'Email was submitted, but PDF cleanup failed. Remove this private PDF before confirming retention cleanup.')
                    messages.success(request, 'Email submitted to Resend with the PDF attached. Delivery can be checked in your Resend dashboard.')
            if not form.errors:
                return redirect('admin:studio_chartemail_preview', draft.pk)
    response = render(request, 'admin/studio/preview.html', context(model_admin, request, title='Preview and send chart email', draft=draft, form=form,
        email_preview=email_html(draft), configured=bool(settings.RESEND_API_KEY and draft.sender)))
    response['Cache-Control'] = 'private, no-store'
    return response
