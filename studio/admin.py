from django.contrib import admin
from django.urls import path, reverse
from django.utils.html import format_html
from . import admin_workflow
from .models import Enquiry, Report

@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "created_at", "resolved"]
    list_filter = ["resolved", "created_at"]
    search_fields = ["name", "email"]

@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["name", "birth_request", "created_by", "created_at", "workflow_links"]
    change_list_template = "admin/studio/report_list.html"
    readonly_fields = ["id", "name", "created_by", "created_at", "workflow_links"]

    @admin.display(description='PDF and email')
    def workflow_links(self, obj):
        if obj.chartemail_set.filter(submitted_at__isnull=False).exists():
            return 'PDF removed after delivery — generate a new PDF to send again'
        download = reverse('admin:studio_report_download', args=[obj.pk])
        if obj.birth_request_id:
            return format_html('<a href="{}">Download PDF</a> · <a href="{}">Compose email</a>', download, reverse('admin:studio_birthrequest_email', args=[obj.birth_request_id]))
        return format_html('<a href="{}">Download PDF</a>', download)

    def get_readonly_fields(self, request, obj=None):
        fields = list(super().get_readonly_fields(request, obj))
        if obj and obj.chartemail_set.exists():
            fields.append('birth_request')
        return fields

    def get_urls(self):
        return [path('generate/', self.admin_site.admin_view(lambda request: admin_workflow.generate(self, request)), name='studio_report_generate'),
                path('<uuid:report_id>/download/', self.admin_site.admin_view(lambda request, report_id: admin_workflow.download(self, request, report_id)), name='studio_report_download')] + super().get_urls()

    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False

from .models import BirthRequest

@admin.register(BirthRequest)
class BirthRequestAdmin(admin.ModelAdmin):
    list_display = ['customer_name', 'email', 'source', 'status', 'report_sent', 'created_at', 'workflow_links']
    list_filter = ['source', 'status', 'report_sent', 'created_at']
    search_fields = ['email', 'payload__name']
    list_editable = ['report_sent']
    readonly_fields = ['id', 'payload', 'source', 'status', 'payment_mode', 'delivery_consent', 'amount_pence', 'currency', 'stripe_session_id', 'created_at', 'paid_at', 'removal_token', 'workflow_links']

    def save_model(self, request, obj, form, change):
        if change and 'email' not in request.POST:
            obj.email = BirthRequest.objects.get(pk=obj.pk).email
        super().save_model(request, obj, form, change)

    @admin.display(description='Prepare and send chart')
    def workflow_links(self, obj):
        generate = reverse('admin:studio_report_generate') + '?request=' + str(obj.pk)
        return format_html('<a href="{}">Generate PDF</a> · <a href="{}">Compose email</a>', generate, reverse('admin:studio_birthrequest_email', args=[obj.pk]))

    def get_urls(self):
        return [path('<uuid:request_id>/email/', self.admin_site.admin_view(lambda request, request_id: admin_workflow.compose(self, request, request_id)), name='studio_birthrequest_email'),
                path('email-preview/<uuid:draft_id>/', self.admin_site.admin_view(lambda request, draft_id: admin_workflow.preview(self, request, draft_id)), name='studio_chartemail_preview')] + super().get_urls()

    @admin.display(description='Customer')
    def customer_name(self, obj):
        return obj.payload.get('name', '')

    def has_add_permission(self, request):
        return False


from .models import Review, Feedback

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'rating', 'approved', 'created_at']
    list_filter = ['approved', 'rating', 'created_at']
    list_editable = ['approved']
    search_fields = ['text']
    readonly_fields = ['rating', 'text', 'created_at', 'birth_request']

    def has_add_permission(self, request):
        return False

@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ['id', 'reviewed', 'created_at']
    list_filter = ['reviewed', 'created_at']
    list_editable = ['reviewed']
    search_fields = ['text']
    readonly_fields = ['text', 'created_at', 'birth_request']
    exclude = ['rating']

    def has_add_permission(self, request):
        return False


from .models import ChartEmail

@admin.register(ChartEmail)
class ChartEmailAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'subject', 'report', 'submitted_at', 'created_by']
    readonly_fields = [field.name for field in ChartEmail._meta.fields]
    search_fields = ['recipient', 'subject', 'provider_id']
    list_filter = ['submitted_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


from .models import DataRemovalRequest
from .privacy import remove_customer
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render


@admin.register(DataRemovalRequest)
class DataRemovalRequestAdmin(admin.ModelAdmin):
    list_display = ['email', 'requested_at', 'approved_at', 'approval_link']
    readonly_fields = ['id', 'birth_request', 'email', 'requested_at', 'approved_at', 'approval_link']
    list_filter = ['approved_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Approve removal')
    def approval_link(self, obj):
        if obj.approved_at:
            return 'Completed — profile removed; accounting exception applies'
        return format_html('<a href="{}">Review and approve deletion</a>', reverse('admin:studio_dataremoval_approve', args=[obj.pk]))

    def get_urls(self):
        return [path('<uuid:removal_id>/approve/', self.admin_site.admin_view(self.approve), name='studio_dataremoval_approve')] + super().get_urls()

    def approve(self, request, removal_id):
        if not self.has_change_permission(request) or not request.user.has_perm('studio.delete_birthrequest'):
            raise PermissionDenied
        removal = get_object_or_404(DataRemovalRequest, pk=removal_id)
        if request.method == 'POST' and request.POST.get('confirm') == 'yes':
            try:
                remove_customer(removal.pk)
            except (OSError, ValueError):
                messages.error(request, 'Deletion could not finish. Check private file permissions; the removal request remains pending.')
            else:
                messages.success(request, 'Customer chart/profile records and files have been removed. Live invoice records remain restricted to accounting.')
                return redirect('admin:studio_dataremovalrequest_changelist')
        return render(request, 'admin/studio/approve_removal.html', admin_workflow.context(self, request, title='Approve data removal', removal=removal))


from .models import Invoice
from .invoicing import invoice_pdf
from django.http import HttpResponse


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['number', 'birth_request', 'issued_at', 'total_pence', 'is_test', 'pdf_link']
    list_filter = ['is_test', 'issued_at']
    readonly_fields = [field.name for field in Invoice._meta.fields] + ['number', 'pdf_link']

    @admin.display(description='PDF invoice')
    def pdf_link(self, obj):
        return format_html('<a href="{}">Download invoice</a>', reverse('admin:studio_invoice_download', args=[obj.pk]))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_urls(self):
        return [path('<int:invoice_id>/download/', self.admin_site.admin_view(self.download), name='studio_invoice_download')] + super().get_urls()

    def download(self, request, invoice_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        invoice = get_object_or_404(Invoice, pk=invoice_id)
        response = HttpResponse(invoice_pdf(invoice), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Venastella_Invoice_{invoice.number}.pdf"'
        return response


import csv
import json


@admin.action(description='Export selected live invoices for accounting (CSV)', permissions=['view'])
def export_accounting_invoices(modeladmin, request, queryset):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="Venastella_Accounting_Invoices.csv"'
    response['Cache-Control'] = 'private, no-store'
    writer = csv.writer(response)
    writer.writerow(['Invoice number', 'Issue date', 'Currency', 'Net', 'VAT', 'Total', 'Customer name', 'Customer email', 'Billing address', 'Seller details', 'Payment reference', 'Line items'])
    def cell(value):
        value = str(value)
        return "'" + value if value.startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value
    for invoice in queryset.filter(is_test=False).order_by('issued_at', 'pk'):
        writer.writerow([invoice.number, invoice.issued_at.isoformat(), invoice.currency.upper(),
                         f'{(invoice.total_pence - invoice.vat_pence) / 100:.2f}', f'{invoice.vat_pence / 100:.2f}', f'{invoice.total_pence / 100:.2f}',
                         cell(invoice.customer.get('name', '')), cell(invoice.customer.get('email', '')),
                         cell(json.dumps(invoice.customer.get('address', {}), ensure_ascii=False)),
                         cell(json.dumps(invoice.issuer, ensure_ascii=False)), cell(invoice.payment_reference), cell(json.dumps(invoice.line_items, ensure_ascii=False))])
    return response

InvoiceAdmin.actions = [export_accounting_invoices]
InvoiceAdmin.date_hierarchy = 'issued_at'
