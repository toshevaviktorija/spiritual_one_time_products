import json, sys
from pathlib import Path
sys.path.insert(0,str(Path('scripts').resolve()))
from natal_chart.models import NatalChartData
from natal_chart.document import NatalChartDocument
from natal_chart.utilities.theme import load_theme
payload=json.load(open('source_files/natal_chart.json'))
item={'point1':{'id':'Sun','name':'Sun','symbol':'☉'},'point2':{'id':'Moon','name':'Moon','symbol':'☽'},'aspect':{'type':'square','name':'Square','symbol':'□','angle':90},'orb':3.77,'interpretation':{'description':'A square describes friction between two sets of needs, impulses or priorities. The tension can encourage action and development, especially when both sides are acknowledged rather than forcing one to silence the other.','meaning':'What you want to express can conflict with what helps you feel secure. Making room for both ambition and emotional needs reduces the pressure to choose one.'}}
payload['data']['aspects']=[item]
data=NatalChartData.from_mapping(payload)
assert len(data.aspects)==1
assert not NatalChartData.from_mapping({'subject_data':{},'chart_data':{}}).aspects
from natal_chart.aspects import AspectSection
from reportlab.platypus import KeepTogether, PageBreak
root=Path.cwd();theme=load_theme(root/'theme/theme.example.json',root)
doc=NatalChartDocument(data,theme,root/'tmp/pdfs/refresh/aspects-preview.pdf')
other={**item,'aspect':{'type':'trine','name':'Trine','symbol':'△'}}
section=AspectSection([item,other,item],doc.styles,doc.palette,doc.symbol_font,doc.panel_width).build()
assert sum(isinstance(x,PageBreak) for x in section)==1
assert sum(isinstance(x,KeepTogether) for x in section)==3
# Render only the user-supplied example, not invented chart interpretations.
doc.build()
print('Input compatibility and grouping checks passed; sample preview generated.')
