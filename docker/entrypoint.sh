#!/bin/sh
set -eu
# Management commands bypass startup tasks (e.g. test, createsuperuser, loaddata).
if [ "${1:-}" = "gunicorn" ]; then
    python manage.py migrate --noinput
    if ! python manage.py cleanup_delivered_reports; then
        echo "Private PDF cleanup needs attention; check the error above." >&2
    fi
    python manage.py collectstatic --noinput
fi
exec "$@"
