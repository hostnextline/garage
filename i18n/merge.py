"""Puts the English dictionary into carnet.html (between <script type="application/json" id="i18n-en"> and </script>).
Sources, later ones win: chunk_*.en.json (the app's texts), extra_*.en.json (texts seen while testing), fixes.json (by hand)."""
import json, glob, re, os
H = os.path.dirname(os.path.abspath(__file__))
d = {}
for pat in ('chunk_*.en.json', 'extra_*.en.json'):
    for f in sorted(glob.glob(os.path.join(H, pat))):
        d.update(json.load(open(f, encoding='utf-8')))
fx = os.path.join(H, 'fixes.json')
if os.path.exists(fx): d.update(json.load(open(fx, encoding='utf-8')))
out = {k: v for k, v in d.items() if isinstance(v, str)}   # (the same text kept too: it is known, not missing)
js = json.dumps(out, ensure_ascii=False, separators=(',', ':'), sort_keys=True).replace('</', '<\\/')
p = '/home/claude/garage/carnet.html'
s = open(p, encoding='utf-8').read()
a = s.index('<script type="application/json" id="i18n-en">') + len('<script type="application/json" id="i18n-en">')
b = s.index('</script>', a)
s = s[:a] + js + s[b:]
open(p, 'w', encoding='utf-8').write(s)
print('entries', len(out), 'bytes', len(js.encode()), 'nulls left', [k for k, v in d.items() if v is None])
