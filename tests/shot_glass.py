import json, os, datetime, sys
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
def mo(k):
    d = T.replace(day=1)
    for _ in range(k): d = (d - datetime.timedelta(days=1)).replace(day=1)
    return d
seed = {'config/main': {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Saleh', 'Ali'], 'rate': 120, 'taxesOn': True, 'goal': 20000, 'prefix': 'F-', 'startNo': 1}}
cl = lambda n, p: {'name': n, 'firstName': n.split()[0], 'lastName': n.split()[1], 'phone': p, 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'}
jobs = [
  ('a1', iso(T), '08:30', 'Saleh', 'termine', cl('Marie Tremblay', '5145550101'), ["Changement d'huile et filtre"], {'number': 'F-0012', 'total': 189.5, 'paid': True, 'issuedAt': iso(T)}),
  ('a2', iso(T), '10:30', 'Saleh', 'route', cl('Paul Roy', '4385550202'), ['Changement de pneus saisonnier'], None),
  ('a3', iso(T), '13:00', 'Ali', 'place', cl('Zoé Gagnon', '5145550303'), ['Freins avant (plaquettes)'], None),
  ('a4', iso(T), '15:30', 'Ali', 'planifie', cl('Luc Bélanger', '4505550404'), ["Changement d'huile et filtre", 'Inspection multipoints'], None),
  ('a5', iso(T + datetime.timedelta(days=1)), '09:00', 'Saleh', 'planifie', cl('Nadia Haddad', '5145550505'), ['Diagnostic'], None),
]
for k in range(1, 6):
    d = mo(k).replace(day=10)
    for i in range(3 + k % 3):
        jobs.append(('h%d%d' % (k, i), iso(d), '10:00', 'Saleh' if i % 2 else 'Ali', 'termine', cl('Client Ancien', '5145550000'), ["Changement d'huile et filtre" if i % 2 else 'Changement de pneus saisonnier'], {'number': 'F-%02d%d' % (k, i), 'total': 900 + 380 * ((k * 7 + i) % 5), 'paid': True, 'issuedAt': iso(d)}))
jobs.append(('u1', iso(mo(0)), '11:00', 'Ali', 'termine', cl('Jean Côté', '5145550606'), ['Alternateur'], {'number': 'F-0013', 'total': 1240.0, 'paid': False, 'issuedAt': iso(mo(0))}))
jobs.append(('u2', iso(mo(0)), '14:00', 'Saleh', 'termine', cl('Sara Lévesque', '5145550707'), ['Freins avant (plaquettes)'], {'number': 'F-0014', 'total': 2380.0, 'paid': True, 'issuedAt': iso(mo(0))}))
for (i, d, t, m, st, c, sv, inv) in jobs:
    j = {'date': d, 'time': t, 'durationMin': 90, 'mechanic': m, 'status': st, 'client': c, 'services': sv, 'service': ', '.join(sv), 'vehicle': {'year': '2018', 'make': 'Honda', 'model': 'Civic'}}
    if inv: j['invoice'] = dict(inv, lines=[{'type': 'mo', 'desc': sv[0], 'qty': 1, 'price': inv['total']}], taxesOn=False, sub=inv['total'], tps=0, tvq=0)
    seed['jobs/' + i] = j
def harness(mode): return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' f'<style>{RESET}</style><script>window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
scheme = sys.argv[1] if len(sys.argv) > 1 else 'light'
width = int(sys.argv[2]) if len(sys.argv) > 2 else 390
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': width, 'height': 844}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    def route(r):
        if r.request.url == 'https://local.test/': r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness({'seed': seed}))
        elif 'fonts.g' in r.request.url: r.continue_()
        else: r.abort()
    pg.route('**/*', route)
    pg.goto('https://local.test/'); pg.wait_for_timeout(900)
    tag = scheme + ('' if width == 390 else str(width))
    pg.screenshot(path=os.path.join(SC, 'g_dash_%s.png' % tag), full_page=True)
    for t in ['agenda', 'clients', 'factures', 'reglages']:
        pg.click('.tab[data-t="%s"]' % t); pg.wait_for_timeout(350)
        pg.screenshot(path=os.path.join(SC, 'g_%s_%s.png' % (t, tag)), full_page=(t != 'agenda'))
    pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(200); pg.click('[data-act="view"][data-v="list"]'); pg.wait_for_timeout(250)
    pg.screenshot(path=os.path.join(SC, 'g_list_%s.png' % tag))
    pg.click('[data-act="open"][data-id="a2"]'); pg.wait_for_timeout(300)
    pg.screenshot(path=os.path.join(SC, 'g_job_%s.png' % tag), full_page=True)
    print('errors', errs, 'hscroll ok', pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'))
    br.close()
