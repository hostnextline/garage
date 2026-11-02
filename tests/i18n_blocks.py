"""English on the new screens (blocks, estimate, waiver, inventory): what would still show in French."""
import datetime, re, json
from team_seed import *
from playwright.sync_api import sync_playwright
T0 = datetime.date.today(); D = T0 + datetime.timedelta(days=1)
while D.weekday() > 4: D += datetime.timedelta(days=1)
D = D.isoformat()
DATA = re.compile(r"Marie|Tremblay|Paul|Roy|Ana|Bob|Saleh|Ali|Hassan|Garage NextLine|Honda|Civic|F-150|Inspection|Huile|Camion \d|^[A-Z]\d[A-Z]|J'autorise|Je comprends|les travaux se font|le garage n'est pas|si d'autres|les pièces que|Le prix estimé")
otok, pw = seed()
c = doc('config/main'); c.pop('bookMode', None); c['homePostal'] = 'H4P 2B5'; c['hours'] = {str(d): {'open': d != 0, 'start': '08:00', 'end': '20:00'} for d in range(7)}; doc_set(otok, 'config/main', c)
for i, pc in enumerate(['H2J 2L3', 'H2X 1H1', 'H2T 1A1']):
    doc_set(otok, 'jobs/b%d' % i, {'date': D, 'time': '08:00', 'block': 'am', 'durationMin': 60, 'mechanic': '', 'truck': '', 'clientId': 'c1', 'client': {'id': 'c1', 'name': 'Ana ' + str(i), 'postal': pc}, 'services': ['Inspection'], 'status': 'planifie', 'createdAt': 5})
doc_set(otok, 'stock/c1__x', {'truck': 'c1', 'name': 'Huile', 'unit': 'L', 'qty': 3}); doc_set(otok, 'stock/c2__x', {'truck': 'c2', 'name': 'Huile', 'unit': 'L', 'qty': 2})
psql("update public.docs set data = jsonb_set(data, '{status}', '\"route\"') where path = 'jobs/j1'")
found = {}
def grab(p, who):
    for m in p.evaluate("Object.keys(window.I18N.misses)"):
        if DATA.search(m) or not re.search(r'[a-zà-ÿ]{3}', m): continue
        found.setdefault(m, set()).add(who)
with sync_playwright() as pl:
    b = pl.chromium.launch()
    for phone in (False, True):
        cx = ctx(b, phone=phone); cx.add_init_script("try { localStorage.setItem('gm.lang', 'en'); } catch(e){}"); p = page(cx, 'p'); login(p, 'hassan@garage.test', pw['hassan'])
        if not phone: p.set_viewport_size({'width': 1366, 'height': 900})
        p.goto(BASE + ('#jour' if phone else '#agenda')); p.wait_for_timeout(600)
        p.evaluate("(d) => { const S = window.__garageApi.S; S.day = d; S.view = 'grid'; window.__garageApi.render(); }", D); p.wait_for_timeout(600)
        if p.locator('[data-act="replan"]').count(): p.click('[data-act="replan"]'); p.wait_for_timeout(2000)
        p.locator('[data-act="blk-book"]').first.click(); p.wait_for_selector('#cs-q, #f-block', state='attached', timeout=8000)
        if p.locator('#cs-q').count(): p.fill('#cs-q', 'Marie'); p.wait_for_timeout(300); p.locator('#cs-results .crow').first.click(); p.wait_for_selector('#f-block', state='attached')
        p.wait_for_timeout(600)
        for sel in ('[data-act="wiz-next"]', '[data-act="wiz-next"]'):
            if p.locator(sel).count() and p.locator(sel).is_visible(): p.click(sel); p.wait_for_timeout(400)
        p.evaluate("document.querySelectorAll('#blkpick .blk')[1] && document.querySelectorAll('#blkpick .blk')[1].click()"); p.wait_for_timeout(400)
        grab(p, 'form'); p.evaluate("const x = document.querySelector('.sheet [data-act=\"sheet-close\"], [data-act=\"back\"]'); x && x.click()"); p.wait_for_timeout(400)
        p.goto(BASE + '#stock'); p.wait_for_timeout(600); grab(p, 'stock')
        p.click('[data-act="stk-new"]'); p.wait_for_timeout(400); grab(p, 'stock-new'); p.evaluate("const x = document.querySelector('.sheet [data-act=\"sheet-close\"]'); x && x.click()")
        p.goto(BASE + '#accueil' if not phone else BASE + '#plus'); p.wait_for_selector('#tiles'); grab(p, 'tiles')
        p.click('#tiles [data-act="est-new"]'); p.wait_for_selector('#est-box'); p.evaluate("[...document.querySelectorAll('#est-box [data-act=\"addsvc\"]')][0].click()"); p.wait_for_timeout(200)
        p.click('[data-act="est-yes"]'); p.wait_for_timeout(400); grab(p, 'estimate'); p.evaluate("const x = document.querySelector('.sheet [data-act=\"sheet-close\"]'); x && x.click()"); p.click('[data-act="est-back"]')
        p.evaluate("(id) => { const S = window.__garageApi.S; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); }", 'j1'); p.wait_for_timeout(500); grab(p, 'job')
        p.click('#wv-nudge [data-act="wv-open"]'); p.wait_for_timeout(400); grab(p, 'waiver'); p.evaluate("const x = document.querySelector('.sheet [data-act=\"sheet-close\"]'); x && x.click()")
        p.evaluate("window.__allSettings = true"); p.goto(BASE + '#reglages'); p.wait_for_selector('#wv-set'); p.wait_for_timeout(400); grab(p, 'settings')
        cx.close()
    b.close()
print('still in French:', len(found))
for k, v in sorted(found.items()): print(sorted(v), '|', k[:200])
print('errors', ERRS[:5])
