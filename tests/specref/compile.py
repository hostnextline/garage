"""Builds the engine reference list from the research files (*.json here, one row per make / model / years / engine, with sources)
and puts a compact copy into carnet.html (<script type="application/json" id="spec-ref">). Also writes specref_all.json (with sources).
Usage: python3 compile.py [path/to/carnet.html]"""
import json, glob, os, re, sys, collections
H = os.path.dirname(os.path.abspath(__file__))
CARNET = sys.argv[1] if len(sys.argv) > 1 else '/home/claude/garage/carnet.html'
FILES = [f for f in sorted(glob.glob(os.path.join(H, '*.json'))) if not re.search(r'(draft_|specref_all)', os.path.basename(f))]
VISC = re.compile(r'^\d{1,2}W-\d{1,2}\b')
def s(x): return re.sub(r'\s+', ' ', str(x if x is not None else '')).strip()
rows, bad = [], []
for f in FILES:
    for r in json.load(open(f)):
        try:
            mk, md = s(r['make']), s(r['model'])
            fr, to = int(r['from']), int(r['to'])
            d = round(float(r['displL']), 1) if r.get('displL') not in ('', None) else None
            cy = int(r['cyl']) if r.get('cyl') not in ('', None) else None
            assert mk and md and 2005 <= fr <= to <= 2027 and d and 0.8 <= d <= 8.5 and cy and 3 <= cy <= 12, 'basic'
            oil = r.get('oilL')
            oil = round(float(oil), 1) if oil not in ('', None) else ''
            if oil != '' and not (2.5 <= oil <= 12.5): bad.append((f, mk, md, fr, 'oilL ' + str(oil))); oil = ''
            visc = s(r.get('oilVisc'))
            if visc and not VISC.match(visc): bad.append((f, mk, md, fr, 'visc ' + visc)); visc = ''
            fuel = {'gas': 'gas', 'hybrid': 'hybrid', 'diesel': 'diesel'}.get(s(r.get('fuel')).lower(), 'gas')
            al = [s(a) for a in (r.get('aliases') or []) if s(a) and s(a).lower() != md.lower()]
            rows.append({'make': mk, 'model': md, 'aliases': al, 'from': fr, 'to': to, 'displL': d, 'cyl': cy, 'turbo': bool(r.get('turbo')), 'fuel': fuel, 'engine': s(r.get('engine')),
                         'oilL': oil, 'oilVisc': visc, 'oilFilter': s(r.get('oilFilter')), 'drainTorque': s(r.get('drainTorque')), 'coolant': s(r.get('coolant')), 'trans': s(r.get('trans')),
                         'brake': s(r.get('brake')), 'plugs': s(r.get('plugs')), 'src': [u for u in (r.get('src') or []) if str(u).startswith('http')], 'conf': s(r.get('conf')) or 'medium'})
        except Exception as e:
            bad.append((f, r.get('make'), r.get('model'), r.get('from'), 'skipped: ' + str(e)))
# a row with nothing useful for a sheet is dropped
rows = [r for r in rows if r['oilL'] != '' or r['oilVisc'] or r['oilFilter']]
# same model, same engine, years that overlap: the later file's row is reported (both kept; the app takes the first)
k = lambda r: (r['make'].lower(), r['model'].lower(), r['displL'], r['cyl'], r['turbo'], r['fuel'])
grp = collections.defaultdict(list)
for r in rows: grp[k(r)].append(r)
over = []
for g in grp.values():
    g.sort(key=lambda r: r['from'])
    for a, b in zip(g, g[1:]):
        if b['from'] <= a['to']: over.append((a['make'], a['model'], a['displL'], (a['from'], a['to']), (b['from'], b['to'])))
rows.sort(key=lambda r: (r['make'].lower(), r['model'].lower(), r['from'], r['displL']))
json.dump(rows, open(os.path.join(H, 'specref_all.json'), 'w'), ensure_ascii=False, indent=1)
compact = [[r['make'], r['model'], '|'.join(r['aliases']), r['from'], r['to'], r['displL'], r['cyl'], 1 if r['turbo'] else 0, r['fuel'], r['engine'],
            r['oilL'], r['oilVisc'], r['oilFilter'], r['drainTorque'], r['coolant'], r['trans'], r['brake'], r['plugs']] for r in rows]
blob = json.dumps(compact, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
html = open(CARNET, encoding='utf8').read()
tag = '<script type="application/json" id="spec-ref">'
if tag in html:
    html = re.sub(re.escape(tag) + r'.*?</script>', lambda m: tag + blob + '</script>', html, count=1, flags=re.S)
else:
    anchor = '<script type="application/json" id="i18n-en">'
    assert anchor in html
    html = html.replace(anchor, tag + blob + '</script>\n' + anchor, 1)
open(CARNET, 'w', encoding='utf8').write(html)
by = collections.Counter(r['make'] for r in rows)
print('rows', len(rows), 'with oil quantity', sum(1 for r in rows if r['oilL'] != ''), 'bytes', len(blob))
print('makes', dict(sorted(by.items())))
print('skipped/fixed', len(bad)); [print('  ', b) for b in bad[:30]]
print('overlaps', len(over)); [print('  ', o) for o in over[:30]]
