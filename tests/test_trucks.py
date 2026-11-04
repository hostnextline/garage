"""3 trucks as the columns of the schedule (2 closed but visible); each truck carries the name of the mechanic who drives it
(nobody assigned by hand); its schedule decides; the mechanics' own availability only without trucks."""
import json, os, datetime, re, sys
from chemins import GARAGE, SAUVEGARDES   # (où est l'app : ici ou dans le dépôt)
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open(GARAGE + '/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
W = T + datetime.timedelta(days=3)
while W.weekday() != 2: W += datetime.timedelta(days=1)          # a Wednesday (garage open 8 h - 17 h)
TH = W + datetime.timedelta(days=1)                               # the Thursday after
base = {'biz': {'name': 'Garage NextLine'}, 'rate': 120, 'taxesOn': True, 'goal': 20000, 'prefix': 'F-', 'startNo': 1}
seed_fresh = {'config/main': dict(base)}                         # no trucks saved yet: 3 trucks by default
seed = {'config/main': dict(base, mechanics=['Saleh', 'Ali'], trucks=[{'id': 'c1', 'name': 'Saleh', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Ali', 'on': False, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]),
        'clients/c9': {'firstName': 'Nadia', 'lastName': 'Haddad', 'phone': '5145550505', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1'},
        'jobs/old1': {'date': iso(W), 'time': '13:00', 'durationMin': 60, 'mechanic': 'Saleh', 'status': 'planifie', 'client': {'name': 'Jean Côté', 'phone': '5145550606'}, 'services': ['Alternateur'], 'service': 'Alternateur'}}
def harness(mode, ui='full'):
    pre = 'try{localStorage.setItem("gm.ui",%s)}catch(e){}' % json.dumps(ui) if ui else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>{pre}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def open_page(br, mode, width=1100, ui='full', hash=''):
    ctx = br.new_context(viewport={'width': width, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA', has_touch=width < 700, **({'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'} if width < 700 else {}))
    if width >= 700: ctx.add_init_script('window.__allSettings = 1')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode, ui)) if r.request.url.startswith('https://local.test/') else r.abort())
    pg.goto('https://local.test/' + hash); pg.wait_for_timeout(700)
    return ctx, pg, errs
def txt(pg, sel): return (pg.locator(sel).first.text_content() or '').replace('\xa0', ' ').replace(' ', ' ')
def store(pg, path): return pg.evaluate('p => window.__store[p] || null', path)
def S(pg, k): return pg.evaluate('k => window.__garageApi.S[k]', k)
def wait(pg, ms=300): pg.wait_for_timeout(ms)
def go_day(pg, d, tab='agenda'): pg.evaluate("([d, t]) => { const S = window.__garageApi.S; S.screen = null; S.tab = t; S.day = d; S.view = 'grid'; S.mech = ''; window.__garageApi.render(); }", [d, tab]); wait(pg)
def heads(pg): return pg.evaluate("[...document.querySelectorAll('.cal-head .colh')].map(h => h.textContent.replace(/\\s+/g,' ').trim())")
def open_slots(pg, col): return pg.evaluate("c => document.querySelectorAll('.col[data-col=\"' + c + '\"] .slot.open').length", col)
def slot_open(pg, col, t): return pg.evaluate("([c, t]) => { const b = document.querySelector('.col[data-col=\"' + c + '\"] .slot[data-t=\"' + t + '\"]'); return b ? b.classList.contains('open') : null; }", [col, t])

with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- a fresh garage: 3 trucks, 2 closed ----------
    ctx, pg, errs = open_page(br, {'seed': seed_fresh})
    go_day(pg, iso(W))
    h = heads(pg)
    check('fresh garage: 3 columns « Camion 1, 2, 3 »', len(h) == 3 and h[0].startswith('Camion 1') and h[1].startswith('Camion 2') and h[2].startswith('Camion 3'), h)
    check('Camion 2 and 3 visible but « Fermé »', 'Fermé' in h[1] and 'Fermé' in h[2] and 'Fermé' not in h[0], h)
    check('Camion 1 open during the garage hours, 2 and 3 closed all day', open_slots(pg, 'c1') > 40 and open_slots(pg, 'c2') == 0 and open_slots(pg, 'c3') == 0, [open_slots(pg, c) for c in ('c1', 'c2', 'c3')])
    pg.click('.col[data-col="c2"] .slot[data-t="10:00"]'); wait(pg)
    check('a closed truck cannot be booked', 'Case fermée' in txt(pg, '#toast') and not pg.locator('#sheet').is_visible())
    pg.click('.colh[data-truck="c2"] [data-act="truck-open"]'); wait(pg, 400)
    check('« Ouvrir » opens Camion 2\'s schedule (« Ouvrir le camion »)', 'Horaire de Camion 2' in txt(pg, '#sch-t') and 'Ouvrir le camion' in txt(pg, '#sched [data-act="sc-save"]'))
    pg.click('#sched [data-act="sc-save"]'); wait(pg, 400)
    tk = (store(pg, 'config/main') or {}).get('trucks') or []
    check('« Ouvrir le camion » saves the 3 trucks with Camion 2 open', [t['on'] for t in tk] == [True, True, False] and (store(pg, 'config/main') or {}).get('goal') == 20000, tk)
    check('Camion 2 now bookable', open_slots(pg, 'c2') > 40)
    pg.click('.col[data-col="c2"] .slot[data-t="10:00"]'); wait(pg, 500)
    check('tapping Camion 2 at 10 h starts a booking', pg.locator('#cs-q').count() == 1)
    pg.click('.sheet-head [data-act="sheet-close"]')
    wait(pg)
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'reglages'; window.__garageApi.render(); }"); wait(pg)
    check('Réglages: « Camions » with 3 rows', pg.locator('#trucks-box .tk-row').count() == 3)
    pg.locator('#trucks-box .tk-row').nth(1).locator('[data-f="on"]').uncheck(); pg.click('#s-save'); wait(pg, 600)
    check('Camion 2 closed again from Réglages (original state)', [t['on'] for t in (store(pg, 'config/main') or {}).get('trucks')] == [True, False, False])
    check('no page errors (fresh)', not errs, errs)
    ctx.close()

    # ---------- a garage with mechanics: each truck carries its mechanic's name ----------
    ctx, pg, errs = open_page(br, {'seed': seed})
    go_day(pg, iso(W))
    h = heads(pg)
    check('the columns are the trucks named after their mechanics (« Saleh », « Ali » closed)', h[0].startswith('Saleh') and h[1].startswith('Ali') and 'Fermé' in h[1] and 'Mécano à choisir' not in ' '.join(h), h)
    check('an old job (no truck, mechanic Saleh) shows in Saleh\'s truck', pg.locator('.col[data-col="c1"] .appt[data-id="old1"]').count() == 1)
    check('truck chips: Tous les camions, Saleh, Ali · fermé…', pg.evaluate("[...document.querySelectorAll('[data-act=\"mech\"]')].map(b => b.textContent)") == ['Tous les camions', 'Saleh', 'Ali · fermé', 'Camion 3 · fermé'])
    check('no « Qui part avec quel camion »', pg.locator('#crewbox, [data-crew]').count() == 0)
    # booking in a truck: the mechanic is the one it is named after
    pg.click('.col[data-col="c1"] .slot[data-t="09:00"]'); wait(pg, 500)
    pg.fill('#cs-q', 'Nadia'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 700)
    check('booking form: the truck « Saleh » and its mechanic Saleh already filled', pg.input_value('#f-truck') == 'c1' and pg.input_value('#f-mech') == 'Saleh', [pg.input_value('#f-truck'), pg.input_value('#f-mech')])
    pg.select_option('#f-truck', 'c2'); wait(pg, 150)
    check('changing to the truck « Ali »: Ali + closed warning', pg.input_value('#f-mech') == 'Ali' and 'camion est fermé' in txt(pg, '#hourmsg'), [pg.input_value('#f-mech'), txt(pg, '#hourmsg')])
    pg.select_option('#f-truck', 'c1'); wait(pg, 150)
    pg.fill('#f-svc-in', 'Diagnostic'); pg.keyboard.press('Enter'); pg.keyboard.press('Escape')
    before = set(pg.evaluate('Object.keys(window.__store)'))
    pg.click('#f-save'); wait(pg, 900)
    nid = [k for k in pg.evaluate('Object.keys(window.__store)') if k.startswith('jobs/') and k not in before]
    nj = store(pg, nid[0]) if nid else {}
    check('saved: truck « Saleh », Saleh, Wednesday 9 h', len(nid) == 1 and nj.get('truck') == 'c1' and nj.get('mechanic') == 'Saleh' and nj.get('time') == '09:00' and nj.get('date') == iso(W), nj)
    go_day(pg, iso(W))
    check('the new job is in the truck « Saleh »', pg.locator('.col[data-col="c1"] .appt[data-id="%s"]' % nid[0][5:]).count() == 1 if nid else False)
    # a day off: his truck closed that day (its schedule decides)
    pg.click('.colh[data-truck="c1"] [data-act="truck-close"]'); wait(pg, 400)
    pg.click('#sheet [data-act="truck-close-go"][data-v="day"]'); wait(pg, 600)
    check('a day off: « Fermer seulement » closes the truck « Saleh » that Wednesday only', open_slots(pg, 'c1') == 0 and ((store(pg, 'hours/c1') or {}).get('dates') or {}).get(iso(W)) == {'on': False}, store(pg, 'hours/c1'))
    go_day(pg, iso(TH)); check('…the Thursday after: open as usual', open_slots(pg, 'c1') > 40)
    pg.evaluate("() => { delete window.__store['hours/c1']; window.__garageApi.S.tkHours = {}; }"); go_day(pg, iso(W))
    # no availability with trucks
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 500)
    check('« Disponibilités » with trucks: « Horaire des camions », the truck\'s schedule decides', 'horaire du camion' in txt(pg, '#main') and pg.locator('[data-act="av-mech"]').count() == 0, txt(pg, '#main')[:160])
    # week view label
    go_day(pg, iso(W)); pg.evaluate("() => { const S = window.__garageApi.S; S.view = 'week'; window.__garageApi.render(); }"); wait(pg)
    check('week view: jobs say their truck (its mechanic\'s name)', 'Saleh' in txt(pg, '.appt[data-id="old1"]'), txt(pg, '.appt[data-id="old1"]'))
    pg.evaluate("() => { const S = window.__garageApi.S; S.view = 'grid'; window.__garageApi.render(); }")
    # settings: one name per truck
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'reglages'; window.__garageApi.render(); }"); wait(pg)
    check('Réglages → Camions: one name per truck, no « Mécano habituel »', pg.locator('#trucks-box [data-f="mech"]').count() == 0 and 'La route de Saleh' in txt(pg, '#trucks-box .tk-row'))
    pg.locator('#trucks-box .tk-row').nth(2).locator('[data-f="name"]').fill('Ali')
    pg.click('#s-save'); wait(pg, 300)
    check('two trucks named « Ali »: refused', 'Un nom par camion' in txt(pg, '#toast') and [t.get('name') for t in (store(pg, 'config/main') or {}).get('trucks', [])][2] == 'Camion 3', txt(pg, '#toast'))
    pg.locator('#trucks-box .tk-row').nth(1).locator('[data-f="name"]').fill('Remorque')   # (Ali takes Camion 3; the old one becomes the trailer)
    pg.click('[data-act="addtruckrow"]'); wait(pg, 100)
    check('« + Ajouter un camion » adds Camion 4 (not in service yet), its name ready to type', pg.locator('#trucks-box .tk-row').count() == 4 and pg.locator('#trucks-box .tk-row').nth(3).get_attribute('data-id') == 'c4' and pg.evaluate("document.activeElement && document.activeElement.id") == 'tk-n-c4')
    pg.click('#s-save'); wait(pg, 600)
    cf = store(pg, 'config/main') or {}
    check('saved: 4 trucks, Camion 3 is now Ali\'s (named « Ali »), the rest of the settings kept', [t['name'] for t in cf.get('trucks')] == ['Saleh', 'Remorque', 'Ali', 'Camion 4'] and cf['trucks'][2]['mech'] == 'Ali' and cf['trucks'][1]['mech'] == '' and cf.get('goal') == 20000 and cf.get('mechanics') == ['Saleh', 'Ali'], cf.get('trucks'))
    pg.evaluate("() => { const c = window.__store['config/main']; c.trucks = c.trucks.slice(0, 3); c.trucks[1].name = 'Ali'; c.trucks[1].mech = 'Ali'; c.trucks[2].name = 'Camion 3'; c.trucks[2].mech = ''; }")   # clean-up (mock)
    pg.evaluate("p => { delete window.__store[p]; }", nid[0] if nid else '')
    check('no page errors', not errs, errs)
    ctx.close()

    # ---------- without trucks: the mechanics' own availability ----------
    ctx, pg, errs = open_page(br, {'seed': dict(seed, **{'config/main': dict(seed['config/main'], trucks=[])})})
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 500)
    check('no trucks: « Disponibilités des mécanos », one chip per mechanic, 7 days', pg.locator('[data-act="av-mech"]').count() == 2 and pg.locator('#av-week .hz').count() == 7 and 'horaire du garage qui compte' in txt(pg, '#av-week'))
    pg.click('#av-week .switch[data-v="3"]'); wait(pg, 400)
    av = store(pg, 'avail/saleh') or {}
    check('Saleh: Wednesday off (saved, applies right away)', av.get('mechanic') == 'Saleh' and av['week']['3']['on'] is False and av['week']['1']['on'] is True, av)
    go_day(pg, iso(W))
    check('Wednesday: Saleh\'s column closed', open_slots(pg, 'Saleh') == 0 and open_slots(pg, 'Ali') > 40, [open_slots(pg, 'Saleh'), open_slots(pg, 'Ali')])
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 400)
    pg.click('[data-act="av-reset"]'); wait(pg, 400)
    check('« Revenir à l\'horaire du garage »: no week (original behaviour)', (store(pg, 'avail/saleh') or {}).get('week') is None)
    check('no page errors (no trucks)', not errs, errs)
    ctx.close()

    # ---------- phone ----------
    ctx, pg, errs = open_page(br, {'seed': seed}, width=390, ui=None)
    go_day(pg, iso(W), 'jour')
    chips = pg.evaluate("[...document.querySelectorAll('.chips.trucks [data-act=\"mech\"]')].map(b => b.textContent)")
    check('phone: truck chips under the date (Tous, Saleh, Ali · fermé, Camion 3 · fermé)', chips == ['Tous', 'Saleh', 'Ali · fermé', 'Camion 3 · fermé'], chips)
    gaps = pg.evaluate("[...document.querySelectorAll('.ph-gap')].map(b => b.dataset.m)")
    check('phone: free time only in the open truck', gaps and all(g in ('', 'c1') for g in gaps), gaps)
    check('phone: no « Qui part avec quel camion ? »', pg.locator('#crew-fold, [data-crew]').count() == 0)
    pg.click('.ph-job[data-id="old1"]'); wait(pg)
    check('phone job: says the truck (« Saleh »)', 'Saleh' in txt(pg, '.top-in .eyebrow'), txt(pg, '.top-in .eyebrow'))
    pg.click('[data-act="back"]'); wait(pg)
    pg.click('.tab[data-t="plus"]'); wait(pg)
    rows = pg.evaluate("[...document.querySelectorAll('#tiles a.tile')].filter(a => !['#jour', '#agenda', '#clients', '#factures'].includes(a.getAttribute('href'))).map(a => a.querySelector('b').textContent)")
    check('phone Plus: no « Disponibilités des mécanos » (the trucks\' schedules decide)', 'Disponibilités des mécanos' not in rows and 'Heures d\'ouverture' in rows, rows)
    pg.click('a[href="#heures"]'); wait(pg)
    check('phone hours: one switch per truck', pg.locator('#hz-trucks .switch').count() == 3)
    pg.click('#hz-trucks .switch[data-v="c2"]'); wait(pg, 400)
    check('phone: the switch of a closed truck opens its schedule', 'Horaire de Ali' in txt(pg, '#sch-t'))
    pg.click('#sched [data-act="sc-save"]'); wait(pg, 400)
    check('phone: « Ali » opened from the switch (« Ouvrir le camion »)', [t['on'] for t in (store(pg, 'config/main') or {}).get('trucks')] == [True, True, False])
    go_day(pg, iso(W), 'jour')
    gaps = pg.evaluate("[...document.querySelectorAll('.ph-gap')].map(b => b.dataset.m)")
    check('phone: Ali\'s free time now listed', 'c2' in gaps or '' in gaps, gaps)
    pg.click('.tab[data-t="plus"]'); wait(pg); pg.click('a[href="#heures"]'); wait(pg); pg.click('#hz-trucks .switch[data-v="c2"]'); wait(pg, 400)
    check('phone: the switch of an open truck asks first (« Êtes-vous sûr ? »)', 'Êtes-vous sûr' in txt(pg, '#sheet'))
    pg.click('#sheet [data-act="truck-close-go"][data-v="all"]'); wait(pg, 400)
    check('phone: « Ali » closed again (original state)', [t['on'] for t in (store(pg, 'config/main') or {}).get('trucks')] == [True, False, False])
    check('no page errors (phone)', not errs, errs)
    ctx.close()
    br.close()
ok = sum(1 for _, c in results if c)
print('%d/%d passed' % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
