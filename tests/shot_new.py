"""Screenshots of the new screens (phone 390 px + one desktop grid) for the report."""
import json, os, datetime, sys
from playwright.sync_api import sync_playwright
from PIL import Image
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
W = T + datetime.timedelta(days=3)
while W.weekday() != 2: W += datetime.timedelta(days=1)
scheme = sys.argv[1] if len(sys.argv) > 1 else 'light'
seed = {'config/main': {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Saleh', 'Ali'], 'rate': 120, 'taxesOn': True, 'prefix': 'F-', 'startNo': 1,
                        'services': [{'name': "Changement d'huile et filtre", 'price': 89.95}],
                        'trucks': [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': False, 'mech': ''}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]},
        'clients/c4': {'firstName': 'Luc', 'lastName': 'Bélanger', 'phone': '4505550404', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'}}
def job(d, t, st, name, sv, cid=None, extra=None):
    j = {'date': d, 'time': t, 'durationMin': 90, 'mechanic': 'Saleh', 'truck': 'c1', 'status': st, 'client': {'name': name, 'phone': '4505550404', 'address': '4520 rue Saint-Denis, Montréal'}, 'services': sv, 'vehicle': {'year': '2018', 'make': 'Honda', 'model': 'Civic'}}
    if cid: j['clientId'] = cid
    j.update(extra or {}); return j
seed['jobs/w1'] = job(iso(W), '08:30', 'planifie', 'Marie Tremblay', ['Freins avant (plaquettes)'])
seed['jobs/w2'] = job(iso(W), '13:00', 'planifie', 'Luc Bélanger', ["Changement d'huile et filtre", 'Inspection multipoints'], 'c4')
seed['jobs/p1'] = job(iso(T - datetime.timedelta(days=20)), '10:00', 'noshow', 'Luc Bélanger', ['Diagnostic'], 'c4')
for i, (v, c, tot, rc) in enumerate([('NAPA', 'pieces', 229.95, True), ('Esso', 'essence', 80.0, False), ('Intact Assurance', 'assur', 300.0, False)]):
    tx = c != 'assur'; sub = round(tot / 1.14975, 2) if tx else tot; tp = round(sub * 0.05, 2) if tx else 0; tq = round(sub * 0.09975, 2) if tx else 0
    seed['expenses/e%d' % i] = {'date': iso(T - datetime.timedelta(days=i)), 'vendor': v, 'cat': c, 'truck': 'c1' if i == 0 else '', 'total': tot, 'tps': tp, 'tvq': tq, 'sub': round(tot - tp - tq, 2), 'taxIncl': tx, 'method': 'Débit', 'receipt': 'receipts/e0' if rc else None, 'createdAt': i}
def harness(ui):
    pre = 'try{localStorage.setItem("gm.ui",%s)}catch(e){}' % json.dumps(ui) if ui else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>{pre}window.__MOCK={json.dumps({"seed": seed})};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
def page(br, w, ui):
    ctx = br.new_context(viewport={'width': w, 'height': 844 if w < 700 else 820}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA', has_touch=w < 700, **({'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'} if w < 700 else {}))
    pg = ctx.new_page(); pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(ui)) if r.request.url == 'https://local.test/' else r.abort())
    pg.goto('https://local.test/'); pg.wait_for_timeout(800); return ctx, pg
def go(pg, js): pg.evaluate("() => { const S = window.__garageApi.S; " + js + "; window.__garageApi.render(); }"); pg.wait_for_timeout(350)
names = []
def shot(pg, n): p = os.path.join(SC, 'n_%s_%s.png' % (n, scheme)); pg.screenshot(path=p); names.append(p)
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg = page(br, 390, None)
    go(pg, "S.tab = 'jour'; S.day = '%s'" % iso(W)); shot(pg, 'jour')
    pg.click('.ph-job[data-id="w2"]'); pg.wait_for_timeout(300); pg.evaluate("window.scrollTo(0, 200)"); pg.wait_for_timeout(150); shot(pg, 'job')
    pg.click('[data-act="cancel"]'); pg.wait_for_timeout(300); shot(pg, 'annuler')
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(200)
    pg.evaluate("window.scrollTo(0, 0)")
    go(pg, "S.screen = 'job'; S.jobId = 'w2'")
    pg.evaluate("() => { const S = window.__garageApi.S; window.__store['jobs/w2'].status = 'place'; }"); pg.wait_for_timeout(100)
    pg.evaluate("() => { const S = window.__garageApi.S; S.jobs.forEach(j => { if (j.id === 'w2') j.status = 'place'; }); window.__garageApi.render(); }"); pg.wait_for_timeout(200)
    pg.click('.nextbtn'); pg.wait_for_timeout(300); shot(pg, 'travaux')
    pg.click('.sheet-head [data-act="sheet-close"]'); pg.wait_for_timeout(200)
    go(pg, "S.screen = null; S.tab = 'dispos'"); shot(pg, 'dispos')
    go(pg, "S.screen = null; S.tab = 'tresor'; S.trView = 'dep'"); shot(pg, 'tresor')
    pg.click('.top-in [data-act="exp-new"]'); pg.wait_for_timeout(200); pg.fill('#x-total', '114,98'); pg.fill('#x-vendor', 'Canadian Tire'); pg.click('[data-act="x-pay"][data-v="Crédit"]'); pg.wait_for_timeout(150); shot(pg, 'depense')
    ctx.close()
    ctx, pg = page(br, 1100, 'full')
    go(pg, "S.tab = 'agenda'; S.view = 'grid'; S.day = '%s'; S.mech = ''" % iso(W)); pg.evaluate("document.getElementById('cal').scrollTop = 0"); pg.screenshot(path=os.path.join(SC, 'n_grille_%s.png' % scheme))
    ctx.close(); br.close()
ims = [Image.open(n).convert('RGB').crop((0, 0, 390, 844)) for n in names]
bg = (233, 222, 210) if scheme == 'light' else (30, 25, 21)
for part, chunk in (('a', ims[:4]), ('b', ims[4:])):
    out = Image.new('RGB', (24 + len(chunk) * 414, 892), bg)
    for i, im in enumerate(chunk): out.paste(im, (24 + i * 414, 24))
    out.save(os.path.join(SC, 'apercu_nouveau_%s_%s.png' % (part, scheme)))
print('ok', len(names))
