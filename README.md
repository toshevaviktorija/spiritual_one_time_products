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
