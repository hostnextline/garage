"""Tableau de bord (Accueil) + glass look, in Claude mode (mock runtime)."""
import json, os, datetime, re
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
def harness(mode): return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' f'<style>{RESET}</style><script>try{{localStorage.setItem("gm.ui","full")}}catch(e){{}}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def open_page(br, mode, width=390, scheme='light', hash=''):
    ctx = br.new_context(viewport={'width': width, 'height': 844}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    def route(r):
        if r.request.url == 'https://local.test/': r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode))
        else: r.abort()
    pg.route('**/*', route); pg.goto('https://local.test/' + hash); pg.wait_for_timeout(700)
    return ctx, pg, errs
def txt(pg, sel): return pg.locator(sel).first.text_content() or ''
def no_hscroll(pg): return pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1')

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs = open_page(br, {'seed': seed})
    check('opens on Accueil', pg.locator('.tab[data-t="accueil"][aria-current="page"]').count() == 1)
    check('tabs: Accueil Agenda Clients Factures Réglages', pg.evaluate("[...document.querySelectorAll('.tab')].filter(b=>!b.hidden).map(b=>b.textContent.trim())") == ['Accueil', 'Agenda', 'Clients', 'Factures', 'Réglages'])
    check('greeting', re.match(r'^(Bonjour|Bonsoir)$', txt(pg, 'h1')) is not None, txt(pg, 'h1'))
    check('month revenue = issued invoices of the month', txt(pg, '.kpi-big').replace('\u202f', ' ').replace('\xa0', ' ') == '3 809,50 $', txt(pg, '.kpi-big'))
    check('change vs last month', txt(pg, '.delta').replace('\xa0', ' ') == '-46 %', txt(pg, '.delta'))
    check('goal progress', '19 % de l\'objectif de 20' in txt(pg, '.pbar-cap'), txt(pg, '.pbar-cap'))
    check('6 month bars, current one highlighted', pg.locator('.bar').count() == 6 and pg.locator('.bar').nth(5).get_attribute('class') == 'bar cur')
    hs = pg.evaluate("[...document.querySelectorAll('.bar i')].map(i => i.getBoundingClientRect().height)")
    check('bar heights follow the amounts (Aug highest, Jul lowest of past)', hs[3] >= max(hs[:5]) - 0.5 and hs[2] <= min(hs[:5]) + 0.5 and hs[3] > hs[2] * 1.4, hs)
    q = pg.evaluate("[...document.querySelectorAll('.qrow')].map(r => [r.querySelector('b').textContent, r.querySelector('.qnum').textContent])")
    check('today counts by status', q == [['Planifiées', '1'], ['En route', '1'], ['Sur place', '1'], ['Terminées', '1']], q)
    check('4 jobs today', '4 jobs' in txt(pg, '[aria-labelledby="d-today"] .pill'))
    rings = pg.evaluate("[...document.querySelectorAll('.ringcard')].map(c => c.textContent.replace(/\\s+/g,' ').trim())")
    check('ring: jobs du jour 1/4', rings[0].startswith('1/4'), rings)
    check('ring: invoices of the month 67 % paid', '67 %' in rings[2] and '2 569,50' in rings[2].replace('\xa0', ' ').replace('\u202f', ' '), rings)
    check('receivables 1 240,00 $ (1 invoice)', '1 240,00' in rings[3].replace('\xa0', ' ').replace('\u202f', ' ') and '1 facture non payée' in rings[3], rings)
    mc = pg.evaluate("[...document.querySelectorAll('.mcard:not(.add) h3')].map(h => h.textContent)")
    check('one card per mechanic + new booking card', mc == ['Saleh', 'Ali'] and pg.locator('.mcard.add').count() == 1, mc)
    check('Saleh: 1 of 2 jobs done today', '50 %' in pg.locator('.mcard').nth(0).text_content() and '1/2' in pg.locator('.mcard').nth(0).text_content())
    nx = pg.evaluate("[...document.querySelectorAll('[aria-labelledby=d-next] .nrow')].map(r => r.dataset.id)")
    check('coming up: en route and on site first, tomorrow included', nx[:2] == ['a2', 'a3'] and 'a5' in nx and 'a1' not in nx, nx)
    sv = pg.evaluate("[...document.querySelectorAll('.hbar')].map(h => [h.querySelector('span').textContent, h.querySelector('b').textContent])")
    check('popular services (30 days)', sv[0] == ["Changement d'huile et filtre", '2'] and ['Freins avant (plaquettes)', '2'] in sv and len(sv) == 5, sv)
    check('dashboard no sideways scroll (390)', no_hscroll(pg))
    check('frosted panels in use', pg.evaluate("getComputedStyle(document.querySelector('.sect')).backdropFilter").find('blur') >= 0)
    pg.locator('.mcard').nth(1).locator('[data-act="dash-mech"]').click(); pg.wait_for_timeout(400)
    check('« Voir son agenda » opens Ali\'s agenda', pg.locator('.tab[data-t="agenda"][aria-current="page"]').count() == 1 and pg.locator('.chip.on[data-act="mech"][data-v="Ali"]').count() == 1)
    pg.click('.tab[data-t="accueil"]'); pg.wait_for_timeout(300)
    pg.click('[data-act="dash-unpaid"]'); pg.wait_for_timeout(400)
    check('« Voir » receivables opens unpaid invoices', pg.locator('.tab[data-t="factures"][aria-current="page"]').count() == 1 and pg.locator('.chip.on[data-v="unpaid"]').count() == 1)
    pg.click('.tab[data-t="accueil"]'); pg.wait_for_timeout(300)
    pg.click('.nrow[data-id="a3"]'); pg.wait_for_timeout(300)
    check('upcoming row opens the job', 'Zoé Gagnon' in txt(pg, 'h1'))
    pg.click('.tab[data-t="accueil"]'); pg.wait_for_timeout(300)
    pg.click('.quick [data-act="quick"]'); pg.wait_for_timeout(400)
    check('« Facture sur place » shortcut starts with the client choice', pg.locator('#cs-q').count() == 1 and pg.locator('#sheet').is_visible())
    pg.click('[data-act="sheet-close"]'); pg.wait_for_timeout(200)
    pg.goto('https://local.test/#reglages'); pg.wait_for_timeout(500)
    check('goal field in Réglages', pg.input_value('#s-goal') == '20000', pg.input_value('#s-goal'))
    pg.fill('#s-goal', '10 000'); pg.click('#s-save'); pg.wait_for_timeout(500)
    check('goal saved', pg.evaluate("window.__store['config/main'].goal") == 10000, pg.evaluate("window.__store['config/main'].goal"))
    pg.click('.tab[data-t="accueil"]'); pg.wait_for_timeout(300)
    check('dashboard follows the new goal', '38 % de l\'objectif de 10' in txt(pg, '.pbar-cap'), txt(pg, '.pbar-cap'))
    pg.goto('https://local.test/#reglages'); pg.wait_for_timeout(400); pg.fill('#s-goal', ''); pg.click('#s-save'); pg.wait_for_timeout(500); pg.click('.tab[data-t="accueil"]'); pg.wait_for_timeout(300)
    check('without goal: paid share of the month', txt(pg, '.pbar-cap').startswith('Payé :'), txt(pg, '.pbar-cap'))
    check('no script errors', not errs, errs[:3])
    ctx.close()

    ctx, pg, errs = open_page(br, {})
    check('empty notebook: dashboard still clear', 'Plus rien à l\'horaire' in pg.text_content('main') and 'Les services des jobs apparaîtront ici' in pg.text_content('main') and '0,00' in txt(pg, '.kpi-big'))
    check('empty notebook: no errors, no sideways scroll', not errs and no_hscroll(pg), errs[:3])
    ctx.close()
    ctx, pg, errs = open_page(br, {'seed': seed, 'readOnly': True})
    check('read-only viewer: no booking or invoice shortcuts', pg.locator('[data-act="new"]').count() == 0 and pg.locator('.quick [data-act="quick"]').count() == 0 and pg.locator('.quick [data-act="tab"]').count() == 1)
    ctx.close()
    ctx, pg, errs = open_page(br, {'seed': seed}, width=320)
    check('320 px wide: no sideways scroll on dashboard', no_hscroll(pg))
    for t in ['agenda', 'clients', 'factures', 'reglages']:
        pg.click('.tab[data-t="%s"]' % t); pg.wait_for_timeout(250)
        check('320 px wide: no sideways scroll on ' + t, no_hscroll(pg))
    ctx.close()
    ctx, pg, errs = open_page(br, {'seed': seed}, width=1280)
    cols = pg.evaluate("getComputedStyle(document.querySelector('.dash-hero')).gridTemplateColumns.split(' ').length")
    check('wide screen: revenue and today side by side', cols == 2, cols)
    ctx.close()
    ctx, pg, errs = open_page(br, {'seed': seed}, scheme='dark')
    check('dark mode: dark glass panels', pg.evaluate("getComputedStyle(document.querySelector('.sect')).backgroundColor").startswith('rgba(36, 30, 27') and not errs, pg.evaluate("getComputedStyle(document.querySelector('.sect')).backgroundColor"))
    ctx.close()
    br.close()
n = sum(1 for _, ok in results if ok); print(f'\n{n}/{len(results)} passed')
