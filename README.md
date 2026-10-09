# Venastella natal chart PDF generator

Creates a themed natal-chart PDF from the API response in `source_files/natal_chart.json`. It understands the current nested `data.fullApiResponse` structure and also accepts the former flat `subject_data` / `chart_data` shape.

The report includes a themed vector birth-chart wheel sourced from `source_files/chart_render.svg`, the Big Three, cosmic makeup, planet and angle profiles, and all twelve house meanings. The twelve houses occupy six pages, with two houses per page. When `data.aspects` is supplied alongside `data.aggregatesPremium`, a grouped Aspects section follows: each aspect type starts on a new page, its general description appears once, and each point pair shows its symbols, right-aligned orb, and individual meaning. The older calculation-only `chart_data.aspects` list is not used for these interpretations. Wheel metadata is parsed directly from the SVG whenever the PDF is generated.

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/natal_chart/generate_natal_chart.py
```

In your editor, select `.venv/bin/python` as the project interpreter. This is required for imports such as `reportlab.lib` and `reportlab.platypus` to resolve.

The PDF is saved as `output/pdf/Venastella_Natal_Chart_Name_Last_Name.pdf`. Explicit input and output paths are also supported:

```bash
python scripts/natal_chart/generate_natal_chart.py source_files/natal_chart.json output/pdf/my_chart.pdf
```

## Structure

- `generate_natal_chart.py` is the small command-line entry point.
- `models.py` normalizes and validates input data.
- `document.py` owns page templates and document assembly.
- `aspects.py` groups and lays out the aspect interpretations; its typography is editable in `theme/design_system.json`.
- `flowables.py` contains reusable ReportLab drawings.
- `utilities/` contains formatting and theme/config helpers.
- `theme/` contains the editable theme and Venastella color tokens.
- `ameaning_files/natal_houses.json` contains the reusable meaning, life area, and keywords for all twelve houses. These universal descriptions are loaded for every chart; sign-specific text still comes from the natal-chart JSON.

Export all supported theme settings with:

```bash
python scripts/natal_chart/generate_natal_chart.py --dump-default-theme theme/my-theme.json
```

### Design presets

All typography and artwork styling lives in `theme/design_system.json`. Each text role has one named preset containing its font, size, line height, colour role, alignment, and spacing. The same file controls the colour and source file for the ornate `separator` and `frame` artwork. The PNG frame and separators use their transparency as a mask and share the configured frame colour when the PDF is rendered.

Pattern keywords live in `ameaning_files/pattern_keywords.json`, keyed by `patterns[].type`. Each supported type provides three centered badges beneath its interpretation title; unknown types omit the badges. The badge borders share the page frame colour.

When `data.interpretationText` is present, Your Celestial Portrait starts on a new page after aspect patterns and before the planetary positions and house cusps tables. It displays opening and closing text, plus Core Strengths, Growth Opportunities, Life Purpose, and Soul Direction. Sections accept plain text or objects with `paragraphs` and `reflectionQuestion`, including JSON-encoded objects. Empty sections are omitted; longer portraits flow onto additional pages. Typography is editable through the `portrait_*` presets in `theme/design_system.json`.

## Django website

The repository also includes a Django storefront and private report studio. The original generator and design files remain in their existing locations and the command-line workflow above still works.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000/` for the storefront, `/studio/` for the staff-only report studio, and `/admin/` to review enquiries and manage staff accounts. No default staff account or password is created.

The storefront collects customer birth details and optionally opens Stripe Checkout for a £39 GBP natal chart. Payments default to disabled. Birth requests and confirmed payments appear in the admin. Automatic birth-chart API integration, customer report delivery and email notifications are not connected yet. The previous enquiry form remains at `/enquiries/`.

In the studio, upload the chart JSON and the matching self-contained SVG as `.json`, `.svg` or `.txt` files, or paste their text (up to 5 MB each). Make sure both belong to the same person. Generation runs in an isolated process with a two-minute timeout and uses the existing theme and report code. Uploaded source files are temporary; generated PDFs are stored under the ignored `private_reports/` directory and are served only to staff. Do not configure a public media route for that directory. Any staff account can see all studio reports.

You can also generate a report through Django:

```bash
python manage.py generate_natal_chart source_files/natal_chart.json /tmp/venastella-preview.pdf --svg source_files/chart_render.svg
```

### Validation

```bash
python manage.py check
python manage.py test studio
python manage.py makemigrations --check --dry-run
python manage.py collectstatic --noinput
```

The tests cover enquiries, private access, invalid uploads, failed generation and actual PDF generation through the studio. Existing sample PDFs are never overwritten by tests.

### Deployment configuration

Local development defaults to SQLite and debug mode. For deployment set these environment variables in your hosting environment (the local Git-ignored `.env` file is loaded automatically; process environment variables take precedence):

- `DJANGO_DEBUG=false`
- `DJANGO_SECRET_KEY` to a long, random secret
- `DJANGO_ALLOWED_HOSTS` to your comma-separated domain names

Use a Python/Django host with persistent database and private report storage, run migrations and collect static files, and serve the WSGI or ASGI application using a production application server. Serve `staticfiles/` as public static assets; never serve `source_files/`, `output/`, `private_reports/` or the repository root. HTTPS is required with production settings. Back up the database and private reports together.

Before public launch, test Stripe checkout with your account and finish report fulfilment, add the applicable privacy/retention policy and enquiry abuse controls, and replace synchronous report generation with a background queue if concurrent demand requires it. This first version is a local foundation, not a deployed shop.

### Customer birth details and Stripe

The form at `/natal-chart/` saves this payload (no chart JSON or SVG is required from customers):

```json
{
  "name": "Emma Johnson",
  "birthData": {
    "year": 1990, "month": 5, "day": 15,
    "hour": 12, "minute": 0, "second": 0,
    "city": "London", "countryCode": "GB"
  }
}
```

Name, email, year, month, day, city and two-letter country code are required. Email is stored separately from the calculation payload. Hour defaults to 12, minute to 0; second defaults to 0. Explicit midnight is preserved. Dates and time ranges are validated. City is free text and country codes are normalised to uppercase, ready for a future Google Places integration. Country codes currently receive two-letter format validation, not a lookup against a country directory.

Set environment variables before starting Django:

```bash
export STRIPE_CHECKOUT_ENABLED=false
```

With the flag off, customers can save birth requests without any Stripe call or charge. These requests are marked **Submitted (payments disabled)**, never Paid. With the flag on, requests await a fixed **3900 pence / GBP** one-time payment. Price and currency come from the server; posted price values are ignored.

To enable checkout, configure `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `PUBLIC_BASE_URL` (your website origin), and `STRIPE_CHECKOUT_ENABLED=true`. Restart Django after changing these values. Start with Stripe test credentials; never commit secrets. Missing credentials prevent checkout from opening.

Register a snapshot-event Stripe webhook at `/stripe/webhook/` for `checkout.session.completed` and `checkout.session.async_payment_succeeded`. For local testing with an already installed Stripe CLI:

```bash
stripe listen --events checkout.session.completed,checkout.session.async_payment_succeeded --forward-to localhost:8000/stripe/webhook/
```

Use the signing secret printed by that listener as `STRIPE_WEBHOOK_SECRET`. The customer form collects the delivery email and pre-fills Stripe Checkout; the birth-data payload remains in the Django database and is not sent to Stripe. Signed webhooks verify the session reference, £39 amount, currency and paid status before updating a request. Duplicate webhooks do not apply payment twice, and a success-page visit never marks a payment received. Webhooks continue to confirm previously started checkouts when the feature flag is turned off; disabling the flag stops new checkouts but does not cancel sessions already opened in Stripe.

Request status pages require the submitting browser session. Staff can inspect every birth request and its exact JSON in `/admin/studio/birthrequest/`. This does not yet call your astrology API or deliver a PDF to a customer; staff report generation remains separate. Stripe SDK operations and signed webhook behaviour are tested locally, but an end-to-end Stripe account checkout requires your credentials.

### Free promotional natal charts

Share `/redeem-free-natal-chart/` for Instagram promotions or other complimentary charts. This page always saves a free redemption without contacting Stripe, even when paid checkout is enabled. It collects name, email, birth date, optional time, city and country code. It uses the same `BirthDetailsForm` and calculation payload as the storefront: missing hour/minute/second become 12/0/0, explicit zero values are preserved, invalid calendar dates and future birth dates are rejected, and email is required and validated.

In `/admin/studio/birthrequest/`, filter **Source → Free promotion** to see the redemption queue. Each record includes the customer's email, exact birth-details JSON and submission time. After preparing and manually emailing their report, tick **Report sent**. You can filter unsent requests and search by name or email. Free redemptions have a zero price, the status **Free redemption**, and no Stripe session. No email is sent automatically. Existing requests keep their original data.

### Calendar picker and Google Places search

Both birth-details pages use a native browser calendar picker. Dates are submitted as `birth_date=YYYY-MM-DD` and converted into the existing `birthData.year/month/day` JSON. The date picker has today's date as its maximum; Django also rejects future dates server-side. Older callers posting separate year/month/day values still work.

Google Places search is optional and appears when `GOOGLE_MAPS_BROWSER_API_KEY` or `GOOGLE_MAPS_API_KEY` is set in the Django process environment. Configure this in your PyCharm run configuration's environment variables, then restart Django. Enable Maps JavaScript API and Places API (New) in the Google Cloud project and ensure billing is enabled. Use a browser key restricted to these APIs and to your website origins, including `http://127.0.0.1:8000/*` and/or `http://localhost:8000/*` for development. Browser API keys are visible to visitors by design; do not reuse an unrestricted server key.

The Google widget searches for localities and retrieves address components. We use `locality.longText` (with a `postal_town.longText` fallback) for the city and `country.shortText` uppercased for the country code. We do not parse the formatted address or use a province as a town. Town and country code are hidden internal values. Users see one town/city search and must select a suggestion; editing the search clears the previous selection. If the key is missing or search fails, the page explains that location search is unavailable rather than showing the internal fields. No key means no Google script is loaded.

Documentation: https://developers.google.com/maps/documentation/javascript/place-autocomplete-new and https://developers.google.com/maps/api-security-best-practices . Live autocomplete needs your configured key; local tests cover date handling and component mapping without making Google requests.

## Docker and PostgreSQL

Docker Compose runs Django with Gunicorn, serves static assets with WhiteNoise, and uses PostgreSQL 17. PostgreSQL waits until healthy before Django starts; the web container runs database migrations and collects static files on startup. The application runs as a non-root user.

Your existing `.env` is used for runtime configuration and excluded from the image and Git. On a fresh checkout, copy `.env.example` to `.env` and supply a random `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`, along with any Google/Stripe keys. The current local `.env` has been preserved and supplied with generated Docker secrets.

```bash
docker compose up -d --build
# Only for a fresh database; the existing local admin account was copied.
docker compose exec web python manage.py createsuperuser
```

Open http://127.0.0.1:8001/ or http://127.0.0.1:8001/admin/ . Port 8001 avoids conflicts with direct PyCharm development on port 8000. Adjust `DOCKER_WEB_PORT` and `DOCKER_PUBLIC_BASE_URL` together if changing the port; include that origin in your Google browser-key referrer restrictions. The database is only reachable within the Compose network and has no published host port.

```bash
docker compose logs --tail=100 web
docker compose exec web python manage.py test studio
docker compose down
```

`docker compose down` stops containers but preserves the named PostgreSQL and private-report volumes. `docker compose down -v` deletes those volumes and their data. Source changes require rebuilding with `docker compose up -d --build`; source code is not bind-mounted. Secret/flag changes require recreating the web container with `docker compose up -d --force-recreate web`.

Docker explicitly selects `DATABASE_BACKEND=postgres`. Direct local runs continue to use SQLite unless you set `DATABASE_BACKEND=postgres` and configure `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER` and `POSTGRES_PASSWORD`. This keeps the current PyCharm workflow and SQLite data intact. Users and records in the two databases are independent after copying; new submissions to port 8000 do not appear on port 8001.

For an initial transfer to an **empty** PostgreSQL application database, export SQLite records to a private, untracked location:

```bash
.venv/bin/python manage.py dumpdata --natural-foreign --natural-primary --exclude contenttypes --exclude auth.permission --exclude sessions --exclude admin.logentry --output /tmp/venastella-transfer.json
docker compose cp /tmp/venastella-transfer.json web:/tmp/venastella-transfer.json
docker compose exec web python manage.py loaddata /tmp/venastella-transfer.json
```

The export includes user password hashes and customer details: keep it private and remove the temporary files after a successful transfer. Copy existing `private_reports/` PDFs into the container's `/app/private_reports/` volume as well. Do not repeat this import against a database with live records. Back up both the PostgreSQL database and report volume together. PostgreSQL backups can be made with `docker compose exec -T db pg_dump -U venastella -d venastella > /private/path/backup.sql` (adapt the database/user if customised).

The Compose defaults are for local development: debug mode is on and the site is bound to loopback. For hosting, configure HTTPS, real domains, production secrets, `DJANGO_DEBUG=false`, storage backups and the public URL. Do not expose the private report volume via a public file server.

### Birth time, reviews and private feedback

The customer forms now show one native time picker and an **I don’t know my birth time** checkbox. Blank or unknown time defaults to 12:00:00. Midnight remains 00:00:00. Separate hour/minute/second inputs are hidden; existing integrations posting these parts remain supported. Town and country code are also hidden and populated by Google Places selection.

`/reviews/` accepts a 1–5 star rating and text (up to 2,000 characters). Customers can choose a public review or private feedback. Reviews start unapproved: only those explicitly approved in **Admin → Reviews** appear publicly. Unchecking Approved removes a review from the public list. **Admin → Private feedback** shows private submissions; these records have no approval/publication field and never appear in public reviews. Ratings are validated in forms and constrained in the database. Submissions are anonymous and do not claim to verify purchases. No notification email is sent automatically.

The reviews page uses a full-width review form and five interactive stars. Clicking star 3 saves a rating of 3; selected stars fill gold. Private feedback is text-only, opened using **Or submit a feedback** and collapsed using **Cancel**. Existing historical feedback ratings are retained internally, while new feedback has no rating. Panels use the PDF theme's gradient stops and 52% translucent surface, with rounded corners.

### Search discovery

`/sitemap.xml` lists only the home, natal-chart, free-redemption and reviews pages. `/robots.txt` announces its absolute URL without listing private routes. Admin, studio, order status and confirmation responses have `X-Robots-Tag: noindex, nofollow`; staff authentication remains required. Public navigation contains no studio login links.

Before deployment, set `PUBLIC_BASE_URL` to the real HTTPS domain (Docker Compose uses `DOCKER_PUBLIC_BASE_URL`) and configure `DJANGO_ALLOWED_HOSTS`. Localhost cannot be discovered by search engines. Once deployed, submit `/sitemap.xml` in Google Search Console. Reviews initially select five stars; customers can explicitly choose any other rating.

### Admin PDF preparation and email delivery

Open **Admin → Birth requests** and choose **Generate PDF** beside the customer. Upload the personalised JSON and matching SVG (.txt is supported), or paste them. The PDF uses the original renderer and private report storage. Open the generated report and choose **Download PDF** to inspect it locally. **Admin → Reports → Generate natal chart PDF** also supports reports without a customer; an existing report can be linked to a birth request in its admin record.

Choose **Compose email** on the birth request. Only PDFs linked to that request are offered. The recipient is shown explicitly; correct their email on the request if needed. Write the subject/message, create a preview, download and inspect the attachment, then tick the inspection confirmation and click **Send email with PDF attached**. The email uses a dark Venastella HTML template and signature, plus a plain-text alternative. Previews never send email.

Configure `RESEND_API_KEY`, `RESEND_FROM_EMAIL` (an address on a verified Resend domain), and optionally `RESEND_REPLY_TO` in the ignored `.env`. Restart/rebuild the application after changing them. No sender is assumed, and sending is disabled until configured. Docker receives these through its existing `env_file`.

Successful API submission records the Resend email ID/time, recipient, sender, report, message and sending admin in **Chart emails**, and marks the birth request as sent. This records provider acceptance, not confirmed inbox delivery; use Resend's dashboard for delivery/bounce status. PDF hashes guard against attachment changes after preview. Duplicate submits of the same preview are protected by a database lock and a Resend idempotency key; retry the same preview after a network failure. Previews expire after 23 hours; check Resend before making a fresh preview after an uncertain submission. Keys remain server-side. Email fields require Django email validation plus a dotted-domain regex; this checks syntax, not mailbox existence.

### Forms and CSRF tokens

Public POST forms fetch a fresh same-origin Django CSRF token just before submitting, preserving entered values when admin sign-in in another tab rotates the token. If the refresh fails, the form stays filled and shows a retry message. `/csrf-token/` is GET-only, uncached and excluded from indexing. Public form pages are uncached, and rejected submissions still receive HTTP 403 with a friendly return link. Django's token and origin validation remain enabled.

The SQLite and PostgreSQL apps have separate CSRF cookie names because localhost cookies are shared across ports; override `DJANGO_CSRF_COOKIE_NAME` if you run additional instances on the same hostname. Session cookie names are unchanged. Reload any tabs opened before this update to load the new form script.

### Data storage and removal

Chart JSON/SVG inputs are processed in temporary directories. PDFs remain in private storage for preparation and local inspection; after Resend accepts submission, the website PDF is deleted and the saved email body/subject/hash are cleared. Basic customer/birth details and delivery metadata remain. This is provider acceptance, not confirmed delivery. The `cleanup_delivered_reports` management command retries file cleanup and clears any older sent message bodies. Docker startup runs it automatically; a file-permission failure is reported rather than silently claiming cleanup succeeded. Unsent PDFs remain available until delivery or approved removal.

The status page, birth form and HTML/plain-text email explain storage. Email includes an unguessable customer removal link. Visiting it is read-only; a CSRF-protected POST creates a **Data removal request** in admin. **Review and approve deletion** shows a confirmation page before the irreversible action. Sending is paused while a removal request is pending.

Approval deletes application birth requests matching the email address, associated reports/private PDFs, chart email records, matching enquiries, linked reviews/feedback, session references and relevant Django admin history. The completed removal record retains only its random audit ID and timestamps, with no email/customer reference. Staff accounts and unrelated customers are preserved. Customers do not have login accounts in this application.

This workflow erases the application's records and files. Already-delivered emails, administrator/customer downloads, backups and Resend/Stripe-held copies are outside that deletion operation and must be handled separately. Historical anonymous reviews/feedback have no customer identity and cannot be retroactively matched; new submissions made in a session owning a birth request are linked so approval can erase them too. Keep this scope visible when responding to a removal request.

### Checkout, test payments and invoices

`Get Your Natal Chart` uses **Checkout**. Set `STRIPE_CHECKOUT_ENABLED=true` and choose `PAYMENT_MODE`:

- `demo`: local, debug-only simulation, no Stripe requests and no card fields. Checkout opens a clearly labelled payment page; explicit POST confirmation creates a simulated payment and test invoice. This cannot run with `DJANGO_DEBUG=false`.
- `test`: real Stripe hosted Checkout using `sk_test_…` and `STRIPE_WEBHOOK_SECRET=whsec_…`. Run Stripe CLI `stripe listen --forward-to localhost:8001/stripe/webhook/`, put its signing secret in `.env`, and recreate the web container. Stripe's 4242 4242 4242 4242 test card accepts a future expiry and any CVC. No real charge is made.
- `live`: requires a matching live Stripe secret key and complete invoice business settings. No live payment is enabled by the demo setup.

Set the legal `INVOICE_BUSINESS_NAME`, full `INVOICE_BUSINESS_ADDRESS`, `INVOICE_BUSINESS_EMAIL`, and `INVOICE_VAT_STATUS` (`not_registered` or `registered`). Registered businesses also need `INVOICE_VAT_NUMBER`; `INVOICE_VAT_RATE` defaults to 0.20. The fixed £39 price is treated as VAT-inclusive if VAT is configured. Missing details are explicitly marked on test invoices; live checkout is blocked until configured. Stripe collects a billing address; birth city is never used as a billing address.

A paid invoice is issued after a verified Stripe payment webhook or explicit local demo confirmation, never from a checkout success redirect. One invoice per request has a stable sequential number, date, customer/issuer snapshots, description, amount and VAT breakdown where applicable. Test invoices clearly say no real payment and are not for accounting use. Webhooks reject test/live mismatches. Repeated webhook deliveries reuse the existing invoice.

The customer thank-you page offers an owner-protected invoice download and data-removal link. **Admin → Invoices** offers staff PDF downloads. PDFs are rendered in memory from invoice records, using `assets/product/logo.png`, and are not saved in public storage. When a paid customer's prepared chart is sent from the existing admin composer, both PDFs are attached, with thanks, review and deletion buttons; test deliveries are labelled in their subject. Chart generation remains the manual JSON/SVG inspection workflow. The checkout flow does not fabricate personalised chart data.

Approved application data removal deletes the customer profile, birth details, reports and test invoices. Live invoice snapshots remain as restricted accounting records, detached from the deleted profile; they contain billing details, line items, issuer details, VAT amounts and payment references, but no birth details or chart. Customer notices explain this exception. **Admin → Invoices** provides a date filter and a selected-invoice CSV export that excludes all test invoices. PDFs are regenerated on demand rather than stored.

For a UK limited company, accounting records normally need to be kept for six years from the end of the financial year they concern, with longer retention in some circumstances. Configure the actual company and VAT details after registration before enabling live checkout. There is no automatic invoice expiry until the company's financial year and retention policy are established; maintain database backups so invoice copies remain complete and readable.

Paid checkout requires an unchecked express-consent checkbox for early digital delivery and records the exact consent, refund wording, version and acceptance time. Change-of-mind refunds are unavailable after delivery begins with that consent; statutory rights for faulty or misdescribed content remain. Free redemption does not require this paid-checkout consent. Historical orders are never given fabricated consent.
