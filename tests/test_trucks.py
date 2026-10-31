"""3 trucks as the columns of the schedule (2 closed but visible), who leaves with which truck, the mechanics' own availability."""
import json, os, datetime, re, sys
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
W = T + datetime.timedelta(days=3)
while W.weekday() != 2: W += datetime.timedelta(days=1)          # a Wednesday (garage open 8 h - 17 h)
TH = W + datetime.timedelta(days=1)                               # the Thursday after
base = {'biz': {'name': 'Garage NextLine'}, 'rate': 120, 'taxesOn': True, 'goal': 20000, 'prefix': 'F-', 'startNo': 1}
seed_fresh = {'config/main': dict(base)}                         # no trucks saved yet: 3 trucks by default
seed = {'config/main': dict(base, mechanics=['Saleh', 'Ali'], trucks=[{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': False, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]),
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
    pg.click('.colh[data-truck="c2"] [data-act="truck-toggle"]'); wait(pg, 400)
    tk = (store(pg, 'config/main') or {}).get('trucks') or []
    check('« Ouvrir ce camion » saves the 3 trucks with Camion 2 open', [t['on'] for t in tk] == [True, True, False] and (store(pg, 'config/main') or {}).get('goal') == 20000, tk)
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

    # ---------- a garage with mechanics ----------
    ctx, pg, errs = open_page(br, {'seed': seed})
    go_day(pg, iso(W))
    h = heads(pg)
    check('header says who drives (Camion 1 · Saleh)', 'Saleh' in h[0] and 'Fermé' in h[1], h)
    check('an old job (no truck, mechanic Saleh) shows in Saleh\'s truck', pg.locator('.col[data-col="c1"] .appt[data-id="old1"]').count() == 1)
    check('truck chips: Tous les camions, Camion 1, Camion 2 · fermé…', pg.evaluate("[...document.querySelectorAll('[data-act=\"mech\"]')].map(b => b.textContent)") == ['Tous les camions', 'Camion 1', 'Camion 2 · fermé', 'Camion 3 · fermé'])
    check('« Qui part avec quel camion » row (open trucks only)', pg.locator('#crewbox select[data-crew]').count() == 1 and pg.input_value('#crewbox select[data-crew="c1"]') == 'Saleh')
    # booking in a truck: the mechanic follows the truck
    pg.click('.col[data-col="c1"] .slot[data-t="09:00"]'); wait(pg, 500)
    pg.fill('#cs-q', 'Nadia'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 700)
    check('booking form: Camion 1 and its mechanic Saleh already filled', pg.input_value('#f-truck') == 'c1' and pg.input_value('#f-mech') == 'Saleh', [pg.input_value('#f-truck'), pg.input_value('#f-mech')])
    pg.select_option('#f-truck', 'c2'); wait(pg, 150)
    check('changing to Camion 2: its mechanic (Ali) + closed warning', pg.input_value('#f-mech') == 'Ali' and 'camion est fermé' in txt(pg, '#hourmsg'), [pg.input_value('#f-mech'), txt(pg, '#hourmsg')])
    pg.select_option('#f-truck', 'c1'); wait(pg, 150)
    pg.fill('#f-svc-in', 'Diagnostic'); pg.keyboard.press('Enter'); pg.keyboard.press('Escape')
    before = set(pg.evaluate('Object.keys(window.__store)'))
    pg.click('#f-save'); wait(pg, 900)
    nid = [k for k in pg.evaluate('Object.keys(window.__store)') if k.startswith('jobs/') and k not in before]
    nj = store(pg, nid[0]) if nid else {}
    check('saved: Camion 1, Saleh, Wednesday 9 h', len(nid) == 1 and nj.get('truck') == 'c1' and nj.get('mechanic') == 'Saleh' and nj.get('time') == '09:00' and nj.get('date') == iso(W), nj)
    go_day(pg, iso(W))
    check('the new job is in Camion 1', pg.locator('.col[data-col="c1"] .appt[data-id="%s"]' % nid[0][5:]).count() == 1 if nid else False)
    # crew of the day
    pg.select_option('#crewbox select[data-crew="c1"]', 'Ali'); wait(pg, 600)
    dd = store(pg, 'days/' + iso(W)) or {}
    check('Ali leaves with Camion 1 that day (saved for that day only)', (dd.get('crew') or {}).get('c1') == 'Ali' and 'Ali' in heads(pg)[0], dd)
    check('the planned jobs of Camion 1 follow (Ali)', (store(pg, nid[0]) or {}).get('mechanic') == 'Ali' and (store(pg, 'jobs/old1') or {}).get('mechanic') == 'Ali' and (store(pg, 'jobs/old1') or {}).get('truck') == 'c1')
    go_day(pg, iso(TH))
    check('the next day: Saleh again (usual mechanic)', 'Saleh' in heads(pg)[0])
    go_day(pg, iso(W)); pg.select_option('#crewbox select[data-crew="c1"]', 'Saleh'); wait(pg, 600)
    check('back to Saleh: jobs follow back', (store(pg, nid[0]) or {}).get('mechanic') == 'Saleh' and (store(pg, 'jobs/old1') or {}).get('mechanic') == 'Saleh')
    # the mechanics' availability
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 500)
    check('« Disponibilités des mécanos »: one chip per mechanic, 7 days', pg.locator('[data-act="av-mech"]').count() == 2 and pg.locator('#av-week .hz').count() == 7 and 'horaire du garage qui compte' in txt(pg, '#av-week'))
    pg.click('#av-week .switch[data-v="3"]'); wait(pg, 400)
    av = store(pg, 'avail/saleh') or {}
    check('Saleh: Wednesday off (saved, applies right away)', av.get('mechanic') == 'Saleh' and av['week']['3']['on'] is False and av['week']['1']['on'] is True, av)
    go_day(pg, iso(W))
    check('Wednesday: Camion 1 closed (Saleh off), header says « congé »', open_slots(pg, 'c1') == 0 and 'congé' in heads(pg)[0], heads(pg))
    pg.select_option('#crewbox select[data-crew="c1"]', 'Ali'); wait(pg, 600)
    check('send Ali with Camion 1 that day: open again', open_slots(pg, 'c1') > 40)
    pg.select_option('#crewbox select[data-crew="c1"]', 'Saleh'); wait(pg, 600)
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 400)
    pg.click('#av-week .switch[data-v="3"]'); wait(pg, 300)
    pg.select_option('select[data-av="start"][data-dw="4"]', '10:00'); wait(pg, 300); pg.select_option('select[data-av="end"][data-dw="4"]', '14:00'); wait(pg, 300)
    av = store(pg, 'avail/saleh') or {}
    check('Saleh: Thursday 10 h to 14 h', av['week']['4'] == {'on': True, 'start': '10:00', 'end': '14:00'} and av['week']['3']['on'] is True, av.get('week'))
    pg.select_option('select[data-av="end"][data-dw="4"]', '09:00'); wait(pg, 300)
    check('end before start refused', (store(pg, 'avail/saleh') or {})['week']['4']['end'] == '14:00' and 'après le début' in txt(pg, '#toast'))
    go_day(pg, iso(TH))
    check('Thursday grid follows Saleh: 9 h closed, 10 h and 13 h 50 open, 14 h closed', [slot_open(pg, 'c1', t) for t in ('09:00', '10:00', '13:50', '14:00')] == [False, True, True, False], [slot_open(pg, 'c1', t) for t in ('09:00', '10:00', '13:50', '14:00')])
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 400)
    pg.fill('#av-off', iso(TH)); pg.click('[data-act="av-off-add"]'); wait(pg, 400)
    check('day off added', (store(pg, 'avail/saleh') or {}).get('off') == [iso(TH)] and pg.locator('[data-act="av-off-del"]').count() == 1)
    go_day(pg, iso(TH)); check('day off closes his truck that day', open_slots(pg, 'c1') == 0)
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'dispos'; window.__garageApi.render(); }"); wait(pg, 400)
    pg.click('[data-act="av-off-del"]'); wait(pg, 300); pg.click('[data-act="av-reset"]'); wait(pg, 400)
    av = store(pg, 'avail/saleh') or {}
    check('« Revenir à l\'horaire du garage »: no week, no day off (original behaviour)', av.get('week') is None and av.get('off') == [], av)
    go_day(pg, iso(TH)); check('Thursday: garage hours again', [slot_open(pg, 'c1', t) for t in ('08:00', '16:50', '17:00')] == [True, True, False])
    # week view label
    pg.evaluate("() => { const S = window.__garageApi.S; S.view = 'week'; window.__garageApi.render(); }"); wait(pg)
    check('week view: jobs say their truck and driver', 'Camion 1 · Saleh' in txt(pg, '.appt[data-id="old1"]'), txt(pg, '.appt[data-id="old1"]'))
    pg.evaluate("() => { const S = window.__garageApi.S; S.view = 'grid'; window.__garageApi.render(); }")
    # settings: rename, usual mechanic, add a truck, other settings kept
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'reglages'; window.__garageApi.render(); }"); wait(pg)
    pg.locator('#trucks-box .tk-row').nth(2).locator('[data-f="name"]').fill('Remorque'); pg.locator('#trucks-box .tk-row').nth(2).locator('[data-f="mech"]').select_option('Ali')
    pg.click('[data-act="addtruckrow"]'); wait(pg, 100)
    check('« + Ajouter un camion » adds Camion 4', pg.locator('#trucks-box .tk-row').count() == 4 and pg.locator('#trucks-box .tk-row').nth(3).get_attribute('data-id') == 'c4')
    pg.click('#s-save'); wait(pg, 600)
    cf = store(pg, 'config/main') or {}
    check('saved: 4 trucks, Remorque driven by Ali, the rest of the settings kept', [t['name'] for t in cf.get('trucks')] == ['Camion 1', 'Camion 2', 'Remorque', 'Camion 4'] and cf['trucks'][2]['mech'] == 'Ali' and cf.get('goal') == 20000 and cf.get('mechanics') == ['Saleh', 'Ali'], cf.get('trucks'))
    pg.evaluate("() => { const c = window.__store['config/main']; c.trucks = c.trucks.slice(0, 3); c.trucks[2].name = 'Camion 3'; c.trucks[2].mech = ''; }")   # clean-up (mock)
    pg.evaluate("p => { delete window.__store[p]; }", nid[0] if nid else '')
    check('no page errors', not errs, errs)
    ctx.close()

    # ---------- phone ----------
    ctx, pg, errs = open_page(br, {'seed': seed}, width=390, ui=None)
    go_day(pg, iso(W), 'jour')
    chips = pg.evaluate("[...document.querySelectorAll('.chips.trucks [data-act=\"mech\"]')].map(b => b.textContent)")
    check('phone: truck chips under the date (Tous, Camion 1 · Saleh, Camion 2 · fermé, Camion 3 · fermé)', chips == ['Tous', 'Camion 1 · Saleh', 'Camion 2 · fermé', 'Camion 3 · fermé'], chips)
    gaps = pg.evaluate("[...document.querySelectorAll('.ph-gap')].map(b => b.dataset.m)")
    check('phone: free time only in the open truck', gaps and all(g in ('', 'c1') for g in gaps), gaps)
    check('phone: « Qui part avec quel camion ? » folded', pg.locator('#crew-fold select[data-crew="c1"]').count() == 1)
    pg.click('.ph-job[data-id="old1"]'); wait(pg)
    check('phone job: says the truck and the mechanic', 'Camion 1' in txt(pg, '.top-in .eyebrow') and 'Saleh' in txt(pg, '.top-in .eyebrow'), txt(pg, '.top-in .eyebrow'))
    pg.click('[data-act="back"]'); wait(pg)
    pg.click('.tab[data-t="plus"]'); wait(pg)
    rows = pg.evaluate("[...document.querySelectorAll('nav.ph-menu .ph-row b')].map(b=>b.textContent)")
    check('phone Plus: « Disponibilités des mécanos »', 'Disponibilités des mécanos' in rows, rows)
    pg.click('a[href="#heures"]'); wait(pg)
    check('phone hours: one switch per truck', pg.locator('#hz-trucks .switch').count() == 3)
    pg.click('#hz-trucks .switch[data-v="c2"]'); wait(pg, 400)
    check('phone: Camion 2 opened from the switch', [t['on'] for t in (store(pg, 'config/main') or {}).get('trucks')] == [True, True, False])
    go_day(pg, iso(W), 'jour')
    gaps = pg.evaluate("[...document.querySelectorAll('.ph-gap')].map(b => b.dataset.m)")
    check('phone: Camion 2 free time now listed', 'c2' in gaps or '' in gaps, gaps)
    pg.click('.tab[data-t="plus"]'); wait(pg); pg.click('a[href="#heures"]'); wait(pg); pg.click('#hz-trucks .switch[data-v="c2"]'); wait(pg, 400)
    check('phone: Camion 2 closed again (original state)', [t['on'] for t in (store(pg, 'config/main') or {}).get('trucks')] == [True, False, False])
    check('no page errors (phone)', not errs, errs)
    ctx.close()
    br.close()
ok = sum(1 for _, c in results if c)
print('%d/%d passed' % (ok, len(results)))
sys.exit(0 if ok == len(results) else 1)
