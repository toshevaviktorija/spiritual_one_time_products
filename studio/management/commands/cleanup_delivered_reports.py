from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from studio.models import ChartEmail


class Command(BaseCommand):
    help = 'Remove website PDFs and message text for charts already submitted for delivery.'

    def handle(self, *args, **options):
        submitted = ChartEmail.objects.filter(submitted_at__isnull=False)
        failures = 0
        for report_id in submitted.values_list('report_id', flat=True).distinct():
            try:
                (settings.PRIVATE_REPORT_ROOT / f'{report_id}.pdf').unlink(missing_ok=True)
            except OSError:
                failures += 1
        submitted.update(message='', subject='Natal chart delivery', pdf_sha256='')
        if failures:
            raise CommandError(f'{failures} PDF file(s) could not be removed. Check private storage permissions.')
        self.stdout.write('Delivered chart PDFs and stored message text cleared.')
