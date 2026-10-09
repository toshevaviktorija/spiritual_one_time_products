from django.urls import path
from . import views
from .privacy import request_removal
from .checkout_demo import demo_checkout, download_invoice

urlpatterns = [path("checkout-demo/<uuid:request_id>/", demo_checkout, name="demo-checkout"), path("orders/<uuid:request_id>/invoice/", download_invoice, name="invoice-download"), path("data-removal/<uuid:token>/", request_removal, name="data-removal"), path("reviews/", views.reviews, name="reviews"), path("redeem-free-natal-chart/", views.redeem_free_natal_chart, name="redeem-free-natal-chart"), path("orders/<uuid:request_id>/", views.birth_status, name="birth-status"), path("stripe/webhook/", views.stripe_webhook, name="stripe-webhook"), path("enquiries/", views.enquire, name="legacy-enquire"), path("", views.home, name="home"), path("natal-chart/", views.birth_details, name="enquire"), path("natal-chart/thanks/", views.thanks, name="enquiry-thanks"), path("studio/", views.studio, name="studio"), path("studio/reports/<uuid:report_id>/download/", views.download, name="report-download"), path("brand.css", views.palette, name="palette")]
