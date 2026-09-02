# Venastella natal chart PDF generator

Creates a themed natal-chart PDF from the API response in `source_files/natal_chart.json`. It understands the current nested `data.fullApiResponse` structure and also accepts the former flat `subject_data` / `chart_data` shape.

The report includes a themed vector birth-chart wheel sourced from `source_files/chart_render.svg`, the overview, lunar phase, every available planet and angle, expanded planet/sign/house interpretations, angle meanings, house meanings, aspects, and technical chart metadata. Wheel metadata is parsed directly from the SVG whenever the PDF is generated.

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
- `sections.py` builds semantic report sections.
- `flowables.py` contains reusable ReportLab drawings.
- `utilities/` contains formatting and theme/config helpers.
- `theme/` contains the editable theme and Venastella color tokens.

Export all supported theme settings with:

```bash
python scripts/natal_chart/generate_natal_chart.py --dump-default-theme theme/my-theme.json
```
