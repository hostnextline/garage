"""Novembre 2026 : (1) la fenêtre « Modifier l'horaire » montre l'heure aux 30 minutes (8 h, 8 h 30, 9 h… ; en anglais 8:00, 8:30, 9:00) ;
(2) à la réservation, plus de champ « Mécano » : seulement le camion (sans camion du tout, le choix du mécano reste : c'est la seule colonne)."""
import json, os, datetime, re
from chemins import GARAGE
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open(GARAGE + '/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
W = T + datetime.timedelta(days=3)
while W.weekday() != 2: W += datetime.timedelta(days=1)          # a Wednesday (garage open 8 h - 17 h)
base = {'biz': {'name': 'Garage NextLine'}, 'rate': 120, 'taxesOn': True, 'prefix': 'F-', 'startNo': 1, 'mechanics': ['Saleh', 'Ali'],
        'trucks': [{'id': 'c1', 'name': 'Saleh', 'on': True, 'mech': ''}, {'id': 'c2', 'name': 'Ali', 'on': True, 'mech': ''}]}
CL = {'firstName': 'Nadia', 'lastName': 'Haddad', 'phone': '5145550505', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1'}
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
ERRS = []
def harness(mode, ui):
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>try{{localStorage.setItem("gm.ui",{json.dumps(ui)})}}catch(e){{}}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
def open_page(br, seed, width=1280, ui='full', lang=None):
    ctx = br.new_context(viewport={'width': width, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA', has_touch=width < 700,
                         **({'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'} if width < 700 else {}))
    if lang: ctx.add_init_script("try { localStorage.setItem('gm.lang', '%s'); } catch(e){}" % lang)
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: ERRS.append(str(e)))
    pg.on('console', lambda m: ERRS.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    body = harness({'seed': seed}, ui)
    pg.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=body) if r.request.url.startswith('https://local.test/') else r.abort())
    pg.goto('https://local.test/'); pg.wait_for_timeout(700)
    return ctx, pg
def wait(pg, ms=300): pg.wait_for_timeout(ms)
def store(pg, path): return pg.evaluate('p => window.__store[p] || null', path)
def go_day(pg, d): pg.evaluate("d => { const S = window.__garageApi.S; S.screen = null; S.tab = 'agenda'; S.day = d; S.view = 'grid'; S.mech = ''; window.__garageApi.render(); }", d); wait(pg)
def gut(pg): return pg.evaluate("[...document.querySelectorAll('#sched .sch-gut span')].map(s => s.textContent.replace(/\\s+/g, ' ').trim())")
def labels(pg): return [x for x in gut(pg) if x]
def open_sched(pg):
    pg.click('[data-act="sched"][data-v="garage"]'); wait(pg, 400)
def close_sched(pg):
    pg.locator('#sched .sch-head [data-act="sc-close"]').click(); wait(pg, 300)
def row_of(pg, t):   # the row of a time in the window: its label, and whether the row has the half-hour line
    return pg.evaluate("t => { const c = document.querySelector('#sched .sch-c[data-t=\"' + t + '\"]'); if (!c) return null; const i = [...c.parentNode.children].indexOf(c); const s = document.querySelectorAll('#sched .sch-gut span')[i]; return [s.textContent.trim(), c.classList.contains('hh'), c.classList.contains('hr'), s.className]; }", t)

with sync_playwright() as p:
    br = p.chromium.launch()
    # ---------- 1. the time every 30 minutes in « Modifier l'horaire » ----------
    for sm, every in ((10, 3), (15, 2), (30, 1)):
        ctx, pg = open_page(br, {'config/main': dict(base, slotMin=sm)})
        go_day(pg, iso(W)); open_sched(pg)
        L = labels(pg); g = gut(pg)
        i8 = L.index('8 h') if '8 h' in L else -1
        check('cases of %d min: the time every 30 min (… 8 h, 8 h 30, 9 h, 9 h 30 …)' % sm, i8 >= 0 and L[i8:i8 + 4] == ['8 h', '8 h 30', '9 h', '9 h 30'], L[:12])
        check('…every half hour of the day has its time, nothing in between (one label every %d case%s)' % (every, 's' if every > 1 else ''),
              all(bool(x) == (k % every == 0) for k, x in enumerate(g)) and all(re.fullmatch(r'\d{1,2} h( 30)?', x) for x in L), g[:10])
        vis = pg.evaluate("(() => { const sc = document.querySelector('#sched .sch-scroll'), dh = document.querySelector('#sched .sch-dh'), c = document.querySelector('#sched .sch-c[data-t=\"08:00\"]'); const r = c.getBoundingClientRect(), s = sc.getBoundingClientRect(), h = dh.getBoundingClientRect(); return [Math.round(r.top - h.bottom), r.bottom <= s.bottom]; })()")
        check('…the window opens on 8 h (the first open case) right under the days, the half hour before it showing', 0 <= vis[0] <= 60 and vis[1], vis)
        check('…8 h 30 on its own row, with a light line; 9 h with the hour line', row_of(pg, '08:30')[:3] == ['8 h 30', True, False] and row_of(pg, '09:00')[:3] == ['9 h', False, True], [row_of(pg, '08:30'), row_of(pg, '09:00')])
        if sm == 10:
            st = pg.evaluate("[getComputedStyle(document.querySelector('#sched .sch-gut span.hr')).fontWeight, getComputedStyle(document.querySelector('#sched .sch-gut span.hh')).fontWeight]")
            check('…the hours a little bolder than the half hours (easy to read)', int(st[0]) > int(st[1]), st)
            pg.screenshot(path='his_sched_30.png')
            close_sched(pg)
        ctx.close()
    ctx, pg = open_page(br, {'config/main': dict(base, slotMin=60)})
    go_day(pg, iso(W)); open_sched(pg)
    L = labels(pg)
    vis = pg.evaluate("(() => { const dh = document.querySelector('#sched .sch-dh'), c = document.querySelector('#sched .sch-c[data-t=\"08:00\"]'); return Math.round(c.getBoundingClientRect().top - dh.getBoundingClientRect().bottom); })()")
    check('cases of 1 hour: opens on 8 h too', 0 <= vis <= 60, vis)
    check('cases of 1 hour: one time per case (8 h, 9 h, 10 h: there is no half hour)', '8 h' in L and '9 h' in L and not any('30' in x for x in L) and len(L) == len(gut(pg)), L[:6])
    ctx.close()
    # English: 8:00, 8:30, 9:00
    ctx, pg = open_page(br, {'config/main': dict(base, slotMin=10)}, lang='en')
    go_day(pg, iso(W)); open_sched(pg); wait(pg, 300)
    L = labels(pg)
    i8 = L.index('8:00') if '8:00' in L else -1
    check('in English: 8:00, 8:30, 9:00, 9:30', i8 >= 0 and L[i8:i8 + 4] == ['8:00', '8:30', '9:00', '9:30'], L[:10])
    pg.screenshot(path='his_sched_30_en.png')
    ctx.close()
    # phone
    ctx, pg = open_page(br, {'config/main': dict(base, slotMin=15)}, width=390, ui='phone')
    pg.evaluate("location.hash = 'heures'"); wait(pg, 500)
    open_sched(pg)
    L = labels(pg)
    i8 = L.index('8 h') if '8 h' in L else -1
    check('phone: the time every 30 min too, nothing cut, no sideways scroll', i8 >= 0 and L[i8:i8 + 3] == ['8 h', '8 h 30', '9 h']
          and pg.evaluate("[...document.querySelectorAll('#sched .sch-gut span')].every(s => s.scrollWidth <= s.clientWidth + 1 || !s.textContent)")
          and pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), L[:6])
    pg.screenshot(path='his_sched_30_phone.png')
    ctx.close()

    # ---------- 2. booking: no « Mécano » field, only the truck ----------
    ctx, pg = open_page(br, {'config/main': dict(base), 'clients/c9': CL})
    go_day(pg, iso(W))
    pg.click('.col[data-col="c2"] .slot[data-t="10:00"]'); wait(pg, 500)
    pg.fill('#cs-q', 'Nadia'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 700)
    form = pg.locator('#jobform')
    labs = pg.evaluate("[...document.querySelectorAll('#jobform label')].map(l => l.textContent.trim())")
    check('booking (trucks): no « Mécano » in the form', not any(l.startswith('Mécano') for l in labs) and pg.locator('#f-mech-show').count() == 0 and pg.locator('select#f-mech').count() == 0, labs)
    check('…only the truck to choose (« Ali », the case touched)', pg.locator('select#f-truck').is_visible() and pg.input_value('#f-truck') == 'c2')
    ft = pg.evaluate("document.getElementById('jobform').textContent")
    check('…no sentence about the mechanic under the truck', 'Le mécano suit le camion' not in ft and 'choisit son camion' not in ft)
    check('…the duration takes the whole width (no empty place where the mechanic was)', pg.evaluate("(() => { const u = document.getElementById('f-units').closest('.field'); return u.parentNode.classList.contains('grid2') ? false : true; })()"))
    pg.screenshot(path='his_book_nomech.png', full_page=False)
    # save it: the job is in the truck « Ali » (the mechanic who drives it that day takes it)
    pg.fill('#f-svc-in', 'Diagnostic'); pg.keyboard.press('Enter'); pg.keyboard.press('Escape')
    before = set(pg.evaluate('Object.keys(window.__store)'))
    pg.click('#f-save'); wait(pg, 900)
    nid = [k for k in pg.evaluate('Object.keys(window.__store)') if k.startswith('jobs/') and k not in before]
    nj = store(pg, nid[0]) if nid else {}
    check('…saved in the truck « Ali », Wednesday 10 h, nobody named yet', len(nid) == 1 and nj.get('truck') == 'c2' and nj.get('time') == '10:00' and nj.get('date') == iso(W) and not nj.get('mechanic'), nj)
    go_day(pg, iso(W))
    check('…and it shows in the truck « Ali »', bool(nid) and pg.locator('.col[data-col="c2"] .appt[data-id="%s"]' % nid[0][5:]).count() == 1)
    ctx.close()
    # phone: the same form, no « Mécano »
    ctx, pg = open_page(br, {'config/main': dict(base), 'clients/c9': CL}, width=390, ui='phone')
    pg.click('.tab-new'); wait(pg, 400); pg.click('[data-act="ph-go"][data-v="new"]'); wait(pg, 500)
    pg.fill('#cs-q', 'Nadia'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 700)
    txtform = pg.evaluate("document.getElementById('jobform') ? document.getElementById('jobform').textContent : ''")
    check('phone booking: no « Mécano » either (only « Camion »)', 'Mécano' not in txtform and 'Camion' in txtform and pg.locator('#f-mech[type="hidden"]').count() == 1, txtform[:200])
    ctx.close()
    # without any truck: the mechanic is still the column, so it stays
    ctx, pg = open_page(br, {'config/main': dict(base, trucks=[]), 'clients/c9': CL})
    go_day(pg, iso(W))
    pg.locator('.col .slot.open').first.click(); wait(pg, 500)
    pg.fill('#cs-q', 'Nadia'); wait(pg); pg.locator('#cs-results .crow').first.click(); wait(pg, 700)
    check('no truck at all (columns = mechanics): the « Mécano » choice stays (it is the column)', pg.locator('select#f-mech').is_visible() and pg.locator('#f-truck').count() == 0)
    ctx.close()
    br.close()
check('no page errors', not ERRS, ERRS[:5])
print('%d/%d passed' % (sum(1 for _, ok in results if ok), len(results)))
