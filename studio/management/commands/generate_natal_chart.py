from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand
from studio.render import render

class Command(BaseCommand):
    help = "Generate a PDF using the existing Venastella report engine"
    def add_arguments(self, parser):
        parser.add_argument("input", type=Path)
        parser.add_argument("output", type=Path)
        parser.add_argument("--svg", type=Path, required=True)
    def handle(self, *args, **options):
        render(options["input"], options["svg"], options["output"])
        self.stdout.write(self.style.SUCCESS(f"Created {options['output']}"))
