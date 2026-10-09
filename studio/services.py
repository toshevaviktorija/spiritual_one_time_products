import subprocess
import sys
import tempfile
from pathlib import Path
from django.conf import settings

def generate_report(chart_json, chart_svg, destination):
    with tempfile.TemporaryDirectory(prefix="venastella-") as directory:
        root = Path(directory)
        for upload, name in ((chart_json, "chart.json"), (chart_svg, "chart.svg")):
            with (root / name).open("wb") as stream:
                for chunk in upload.chunks():
                    stream.write(chunk)
        subprocess.run([sys.executable, "-m", "studio.render", str(root / "chart.json"), str(root / "chart.svg"), str(destination)], cwd=settings.BASE_DIR, check=True, capture_output=True, timeout=120)
