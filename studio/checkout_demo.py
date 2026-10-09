from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_GET
from .models import BirthRequest
from .invoicing import ensure_invoice, invoice_pdf


@never_cache
@require_http_methods(['GET', 'POST'])
def demo_checkout(request, request_id):
    if not settings.DEBUG or settings.PAYMENT_MODE != 'demo' or not settings.STRIPE_CHECKOUT_ENABLED:
        raise Http404()
    if str(request_id) not in request.session.get('birth_requests', []):
        raise Http404()
    customer = get_object_or_404(BirthRequest, pk=request_id, payment_mode='demo', source='storefront')
    if customer.status == 'paid':
        return redirect('birth-status', request_id=customer.pk)
    if customer.status != 'pending':
        raise Http404()
    if request.method == 'POST':
        with transaction.atomic():
            customer = BirthRequest.objects.select_for_update().get(pk=customer.pk)
            customer.status = 'paid'
            customer.paid_at = timezone.now()
            customer.save(update_fields=['status', 'paid_at'])
            ensure_invoice(customer, {'name': customer.payload.get('name', '')})
        return redirect('birth-status', request_id=customer.pk)
    return render(request, 'studio/demo_checkout.html', {'birth_request': customer})


@never_cache
@require_GET
def download_invoice(request, request_id):
    if str(request_id) not in request.session.get('birth_requests', []):
        raise Http404()
    customer = get_object_or_404(BirthRequest, pk=request_id, status='paid')
    invoice = ensure_invoice(customer)
    response = HttpResponse(invoice_pdf(invoice), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Venastella_Invoice_{invoice.number}.pdf"'
    return response
