import json
import logging
import subprocess
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET
from .forms import EnquiryForm, ReportForm
from .models import Report
from .services import generate_report

logger = logging.getLogger(__name__)

def home(request):
    return render(request, "studio/home.html")

def enquire(request):
    form = EnquiryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("enquiry-thanks")
    return render(request, "studio/enquire.html", {"form": form})

def thanks(request):
    return render(request, "studio/thanks.html")

@staff_member_required
def studio(request):
    form = ReportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        report = Report(name=form.chart_data.name[:200], created_by=request.user)
        destination = settings.PRIVATE_REPORT_ROOT / f"{report.id}.pdf"
        try:
            generate_report(form.cleaned_data["chart_json"], form.cleaned_data["chart_svg"], destination)
            report.save()
        except (subprocess.SubprocessError, OSError):
            destination.unlink(missing_ok=True)
            logger.exception("Report generation failed")
            form.add_error(None, "We could not generate this report. Check that the JSON and SVG match and contain complete chart data.")
        else:
            messages.success(request, "Your report is ready.")
            return redirect("studio")
    return render(request, "studio/studio.html", {"form": form, "reports": Report.objects.exclude(chartemail__submitted_at__isnull=False)[:50]})

@staff_member_required
@require_GET
def download(request, report_id):
    report = get_object_or_404(Report, pk=report_id)
    path = settings.PRIVATE_REPORT_ROOT / f"{report.id}.pdf"
    if not path.is_file():
        raise Http404("Report file unavailable")
    response = FileResponse(path.open("rb"), as_attachment=True, filename="Venastella_Natal_Chart.pdf")
    response["Cache-Control"] = "private, no-store"
    return response

@require_GET
def palette(request):
    colors = json.loads((settings.BASE_DIR / "theme/colors.json").read_text())
    keys = ["background", "surface", "border", "goldLightest", "gold", "palePurple", "primaryLight"]
    from scripts.natal_chart.utilities.theme import load_theme
    theme = load_theme(settings.BASE_DIR / 'theme/theme.example.json', settings.BASE_DIR)
    gradient = ','.join(f'{shade} {stop * 100:g}%' for shade, stop in zip(theme['colors']['border_gradient_colors'], theme['colors']['border_gradient_locations']))
    extras = f";--panel-border-gradient:linear-gradient(90deg,{gradient});--panel-surface:{theme['colors']['panel_surface']}"
    css = ":root{" + ";".join(f"--{key}:{colors[key]}" for key in keys) + extras + "}"
    return HttpResponse(css, content_type="text/css")

import stripe
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_http_methods
from .forms import BirthDetailsForm
from .models import BirthRequest
from .payments import CheckoutAlreadyCompleted, create_checkout, checkout_configuration_error
from .invoicing import ensure_invoice, live_invoice_ready
from .terms import REFUND_TERMS, DELIVERY_CONSENT, TERMS_VERSION


@require_http_methods(['GET', 'POST'])
def birth_details(request):
    return _birth_request_page(request)


@require_http_methods(['GET', 'POST'])
def redeem_free_natal_chart(request):
    return _birth_request_page(request, free_redemption=True)


def _birth_request_page(request, free_redemption=False):
    enabled = settings.STRIPE_CHECKOUT_ENABLED and not free_redemption
    form = BirthDetailsForm(request.POST if request.method == 'POST' else None, require_delivery_consent=enabled)
    if request.method == 'POST' and form.is_valid():
        if enabled and (error := checkout_configuration_error()):
            form.add_error(None, error)
        else:
            previous = request.session.get('active_birth_request')
            birth_request = BirthRequest.objects.filter(pk=previous).first() if previous else None
            payload = form.payload()
            if not birth_request or birth_request.payload != payload or birth_request.email != form.cleaned_data['email'] or birth_request.source != BirthRequest.Source.STOREFRONT or birth_request.status != BirthRequest.Status.PENDING or not enabled:
                birth_request = BirthRequest.objects.create(
                    payload=payload, email=form.cleaned_data['email'], payment_mode=settings.PAYMENT_MODE,
                    delivery_consent={} if not form.cleaned_data.get('early_delivery_consent') else {'accepted_at': timezone.now().isoformat(), 'consent': DELIVERY_CONSENT, 'refund_terms': REFUND_TERMS, 'version': TERMS_VERSION},
                    source=BirthRequest.Source.PROMOTION if free_redemption else BirthRequest.Source.STOREFRONT,
                    amount_pence=0 if free_redemption else 3900,
                    status=BirthRequest.Status.FREE if free_redemption else (BirthRequest.Status.PENDING if enabled else BirthRequest.Status.SUBMITTED),
                )
            request.session['active_birth_request'] = str(birth_request.id)
            owned = request.session.get('birth_requests', [])
            if str(birth_request.id) not in owned:
                request.session['birth_requests'] = (owned + [str(birth_request.id)])[-50:]
            if not enabled:
                return redirect('birth-status', request_id=birth_request.id)
            if settings.PAYMENT_MODE == 'demo':
                return redirect('demo-checkout', request_id=birth_request.pk)
            try:
                checkout = create_checkout(birth_request)
                birth_request.stripe_session_id = checkout.id
                birth_request.save(update_fields=['stripe_session_id'])
            except CheckoutAlreadyCompleted:
                return redirect('birth-status', request_id=birth_request.id)
            except stripe.StripeError:
                # Do not log provider errors that might contain customer information.
                logger.warning('Stripe Checkout creation failed for request %s', birth_request.id)
                form.add_error(None, 'We could not open checkout. Please try again; your details are saved.')
            else:
                return redirect(checkout.url)
    return render(request, 'studio/birth_details.html', {'form': form, 'payments_enabled': enabled, 'free_redemption': free_redemption, 'refund_terms': REFUND_TERMS, 'payment_mode': settings.PAYMENT_MODE, 'google_places_config': {'apiKey': settings.GOOGLE_MAPS_BROWSER_API_KEY} if settings.GOOGLE_MAPS_BROWSER_API_KEY else None})


@require_GET
def birth_status(request, request_id):
    if str(request_id) not in request.session.get('birth_requests', []):
        raise Http404()
    birth_request = get_object_or_404(BirthRequest, pk=request_id)
    response = render(request, 'studio/birth_status.html', {'birth_request': birth_request, 'refund_terms': REFUND_TERMS, 'cancelled': request.GET.get('cancelled') == '1', 'payments_enabled': settings.STRIPE_CHECKOUT_ENABLED})
    response['Cache-Control'] = 'private, no-store'
    return response


@csrf_exempt
@require_POST
def stripe_webhook(request):
    # Keep accepting payments already in flight when new checkout is disabled.
    if not settings.STRIPE_WEBHOOK_SECRET:
        return HttpResponse(status=503)
    try:
        event = stripe.Webhook.construct_event(request.body, request.headers.get('Stripe-Signature', ''), settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.SignatureVerificationError):
        return HttpResponse(status=400)
    if event['type'] not in {'checkout.session.completed', 'checkout.session.async_payment_succeeded'}:
        return HttpResponse(status=200)
    checkout = event['data']['object']
    if checkout.get('payment_status') != 'paid':
        return HttpResponse(status=200)
    reference = checkout.get('metadata', {}).get('birth_request_id')
    if not reference:
        return HttpResponse(status=200)
    try:
        with transaction.atomic():
            birth_request = BirthRequest.objects.select_for_update().get(pk=reference)
            if (checkout.get('id') != birth_request.stripe_session_id or checkout.get('client_reference_id') != str(birth_request.id) or checkout.get('amount_total') != birth_request.amount_pence or checkout.get('currency') != birth_request.currency or checkout.get('mode') != 'payment'):
                return HttpResponse(status=400)
            if birth_request.payment_mode == 'demo' or bool(event.get('livemode', False)) != (birth_request.payment_mode == 'live'):
                return HttpResponse(status=400)
            if birth_request.status != BirthRequest.Status.PAID:
                birth_request.status = BirthRequest.Status.PAID
                birth_request.paid_at = timezone.now()
                birth_request.email = birth_request.email or (checkout.get('customer_details') or {}).get('email') or ''
                birth_request.save(update_fields=['status', 'paid_at', 'email'])
            ensure_invoice(birth_request, checkout.get('customer_details') or {})
    except (BirthRequest.DoesNotExist, ValueError, ValidationError):
        return HttpResponse(status=400)
    return HttpResponse(status=200)


from django.core.paginator import Paginator
from .forms import ReviewForm, FeedbackForm
from .models import Review

@require_http_methods(['GET', 'POST'])
def reviews(request):
    kind = request.POST.get('submission_type') if request.method == 'POST' else None
    if request.method == 'POST' and kind not in {'review', 'feedback'}:
        return HttpResponse(status=400)
    review_form = ReviewForm(request.POST if kind == 'review' else None, prefix='review')
    feedback_form = FeedbackForm(request.POST if kind == 'feedback' else None, prefix='feedback')
    form = review_form if kind == 'review' else feedback_form
    if request.method == 'POST' and form.is_valid():
        entry = form.save(commit=False)
        active = request.session.get('active_birth_request')
        if active and active in request.session.get('birth_requests', []):
            entry.birth_request = BirthRequest.objects.filter(pk=active).first()
        entry.save()
        messages.success(request, 'Thank you. Your review is awaiting approval.' if kind == 'review' else 'Thank you. Your feedback was saved privately for the Venastella team.')
        return redirect('reviews')
    approved = Paginator(Review.objects.filter(approved=True), 20).get_page(request.GET.get('page'))
    return render(request, 'studio/reviews.html', {'review_form': review_form, 'feedback_form': feedback_form, 'reviews': approved})
