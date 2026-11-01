"""Screenshots of every screen (2 themes, PC + phone) into px_<label>/, to compare before / after a CSS cleanup.
python3 css_pixels.py before|after ; python3 css_pixels.py compare"""
import sys, os, json
from PIL import Image, ImageChops
lab = sys.argv[1]
if lab == 'compare':
    out = []
    for f in sorted(os.listdir('px_before')):
        if not os.path.exists('px_after/' + f): out.append((f, 'missing')); continue
        a, b = Image.open('px_before/' + f).convert('RGB'), Image.open('px_after/' + f).convert('RGB')
        if a.size != b.size: out.append((f, 'size %s vs %s' % (a.size, b.size))); continue
        d = ImageChops.difference(a, b); bb = d.getbbox()
        n = sum(1 for px in d.getdata() if max(px) > 24) if bb else 0
        out.append((f, n, bb))
    bad = [o for o in out if o[1] != 0]
    for o in out: print(o)
    print('screens:', len(out), 'different:', len(bad))
    sys.exit(0)
from team_seed import *
from playwright.sync_api import sync_playwright
os.makedirs('px_' + lab, exist_ok=True)
otok, pw = seed()
psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
SCREENS = ['accueil', 'agenda', 'clients', 'factures', 'tresor', 'dispos', 'stock', 'reglages', 'equipe']
FREEZE = """(() => { const st = document.createElement('style'); st.textContent = '*,*::before,*::after{transition:none!important;animation:none!important;caret-color:transparent!important} .leaflet-tile-pane,.leaflet-pane{visibility:hidden!important}'; document.head.appendChild(st);
  for (const e of document.querySelectorAll('*')) { if (e.children.length === 0 && /il y a \\d|\\d+ s\\b|\\d+ min\\b/.test(e.textContent || '')) e.textContent = '—'; } })()"""
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for theme in ('', 'emeraude'):
        psql("update public.docs set data = jsonb_set(data, '{lux}', '\"%s\"'::jsonb) where path='config/main'" % (theme or 'sable'))
        for phone in (False, True):
            c = ctx(b, phone=phone); p = page(c, 'hassan')
            if not phone: p.set_viewport_size({'width': 1366, 'height': 900})
            login(p, 'hassan@garage.test', pw['hassan']); p.wait_for_timeout(1500)
            for sc in SCREENS + ['job']:
                if sc == 'job': p.evaluate("(() => { const a = window.__garageApi; location.hash = 'agenda'; })()"); p.wait_for_timeout(500); p.evaluate("(() => { const b = document.querySelector('[data-act=\"open\"]'); if (b) b.click(); })()")
                else: p.evaluate("location.hash = '%s'" % sc)
                p.wait_for_timeout(900); p.evaluate("window.scrollTo(0,0)"); p.evaluate(FREEZE); p.wait_for_timeout(150)
                p.screenshot(path='px_%s/%s_%s_%s.png' % (lab, theme or 'sable', 'ph' if phone else 'pc', sc), full_page=True)
            c.close()
    psql("update public.docs set data = jsonb_set(data, '{lux}', '\"sable\"'::jsonb) where path='config/main'")
    b.close()
print('ok', len(os.listdir('px_' + lab)))
