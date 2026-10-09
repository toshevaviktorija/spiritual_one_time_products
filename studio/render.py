"""Isolated worker using the unchanged PDF engine and original theme."""
import sys
from pathlib import Path
from scripts.natal_chart.document import NatalChartDocument
from scripts.natal_chart.models import NatalChartData
from scripts.natal_chart.utilities.theme import load_theme

def render(input_path, svg_path, output_path):
    root = Path(__file__).resolve().parent.parent
    theme = load_theme(root / "theme/theme.example.json", root)
    theme["chart_page"]["svg_file"] = str(Path(svg_path).resolve())
    NatalChartDocument(NatalChartData.from_file(Path(input_path)), theme, Path(output_path)).build()

if __name__ == "__main__":
    render(*sys.argv[1:])
