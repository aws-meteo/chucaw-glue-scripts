import pathlib, re
base = pathlib.Path('lista_de_glue50.txt')
provided=set()
if base.exists():
    for ln in base.read_text(encoding='utf-8', errors='ignore').splitlines():
        m = re.match(r'\\s*([A-Za-z0-9_.-]+)==', ln)
        if m: provided.add(m.group(1).lower().replace('_','-'))
wh = pathlib.Path('dist/glue-wheelhouse')
excluded=[]
for w in wh.glob('*.whl'):
    dist = w.name.split('-',1)[0].lower().replace('_','-')
    if dist in provided:
        excluded.append(w.name); w.unlink()
print('Excluded:', sorted(excluded))
print('Included:', sorted(p.name for p in wh.glob('*.whl')))
