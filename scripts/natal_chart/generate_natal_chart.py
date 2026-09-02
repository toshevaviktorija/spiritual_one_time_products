#!/usr/bin/env python3
"""Generate a polished natal chart PDF from the Venastella JSON response."""

from __future__ import annotations

import argparse
from pathlib import Path

if __package__ in (None, ""):
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from natal_chart.document import NatalChartDocument
    from natal_chart.models import NatalChartData
    from natal_chart.utilities.formatting import safe_filename
    from natal_chart.utilities.theme import dump_default_theme, load_theme
else:
    from .document import NatalChartDocument
    from .models import NatalChartData
    from .utilities.formatting import safe_filename
    from .utilities.theme import dump_default_theme, load_theme


def parse_args(project_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?", default=project_root / "source_files" / "natal_chart.json", help="Natal chart JSON file")
    parser.add_argument("output", type=Path, nargs="?", help="Destination PDF; defaults to output/pdf/Venastella_Natal_Chart_<name>.pdf")
    parser.add_argument("--output-dir", type=Path, default=project_root / "output" / "pdf", help="Directory used for automatically named PDFs")
    parser.add_argument("--theme", type=Path, default=project_root / "theme" / "theme.example.json", help="Theme JSON file")
    parser.add_argument("--dump-default-theme", type=Path, help="Write every available theme setting and exit")
    return parser.parse_args()


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    args = parse_args(project_root)
    if args.dump_default_theme:
        dump_default_theme(args.dump_default_theme)
        return
    data = NatalChartData.from_file(args.input)
    theme = load_theme(args.theme, project_root)
    output = args.output or args.output_dir / f"Venastella_Natal_Chart_{safe_filename(data.name)}.pdf"
    NatalChartDocument(data, theme, output).build()
    print(f"Created {output}")


if __name__ == "__main__":
    main()
