import os
from pathlib import Path
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "development-only-venastella-change-before-deployment")
if not DEBUG and SECRET_KEY.startswith("development-only"):
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=false")
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "studio"]
MIDDLEWARE = ["studio.middleware.SearchIndexingMiddleware", "django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"
DATABASE_BACKEND = os.environ.get("DATABASE_BACKEND", "sqlite")
if DATABASE_BACKEND == "postgres":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "venastella"),
        "USER": os.environ.get("POSTGRES_USER", "venastella"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 10},
    }}
elif DATABASE_BACKEND == "sqlite":
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
else:
    raise ImproperlyConfigured("DATABASE_BACKEND must be postgres or sqlite")
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Europe/London"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [("brand", BASE_DIR / "assets")]
# Never expose this directory using a public media URL.
PRIVATE_REPORT_ROOT = BASE_DIR / "private_reports"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000

# Restart the application after changing environment flags.
STRIPE_CHECKOUT_ENABLED = os.environ.get('STRIPE_CHECKOUT_ENABLED', 'false').lower() == 'true'
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', 'http://127.0.0.1:8000').rstrip('/')

# Browser key: restrict to your website origins and Google Maps/Places APIs.
GOOGLE_MAPS_BROWSER_API_KEY = os.environ.get('GOOGLE_MAPS_BROWSER_API_KEY') or os.environ.get('GOOGLE_MAPS_API_KEY', '')

RESEND_API_KEY = os.environ.get('RESEND_API_KEY', '')
RESEND_FROM_EMAIL = os.environ.get('RESEND_FROM_EMAIL', '')
RESEND_REPLY_TO = os.environ.get('RESEND_REPLY_TO', '')

# Cookies are shared across localhost ports; isolate the SQLite and Docker apps.
CSRF_COOKIE_NAME = os.environ.get('DJANGO_CSRF_COOKIE_NAME', f'venastella_{DATABASE_BACKEND}_csrf')
CSRF_FAILURE_VIEW = 'studio.csrf.failure'

# demo is a local, no-charge simulator; test uses Stripe's sandbox keys.
PAYMENT_MODE = os.environ.get('PAYMENT_MODE', 'test')
if PAYMENT_MODE not in {'demo', 'test', 'live'}:
    raise ImproperlyConfigured('PAYMENT_MODE must be demo, test or live')
if PAYMENT_MODE == 'demo' and not DEBUG:
    raise ImproperlyConfigured('Local demo checkout requires DJANGO_DEBUG=true')
INVOICE_BUSINESS_NAME = os.environ.get('INVOICE_BUSINESS_NAME', 'Venastella')
INVOICE_BUSINESS_ADDRESS = os.environ.get('INVOICE_BUSINESS_ADDRESS', '')
INVOICE_BUSINESS_EMAIL = os.environ.get('INVOICE_BUSINESS_EMAIL', 'info@venastella.com')
INVOICE_VAT_STATUS = os.environ.get('INVOICE_VAT_STATUS', 'unconfigured')
INVOICE_VAT_NUMBER = os.environ.get('INVOICE_VAT_NUMBER', '')
INVOICE_VAT_RATE = os.environ.get('INVOICE_VAT_RATE', '0.20')
