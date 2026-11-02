"""Parts per engine, truck stock (taken off when the work is saved), photos/signature/extra work in the single-page version (claude.ai / essai)."""
import json, os, datetime, re, sys
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
CIVIC = {'year': '2018', 'make': 'Honda', 'model': 'Civic', 'displL': 2, 'cyl': 4, 'engine': '2,0 L 4 cyl.'}
seed = {'config/main': {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Saleh', 'Ali'], 'rate': 120, 'taxesOn': True, 'prefix': 'F-', 'startNo': 1,
                        'services': [{'name': "Changement d'huile et filtre", 'price': 89.95}, {'name': 'Freins avant (plaquettes)', 'price': 249.0}],
                        'trucks': [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]},
        'specs/2018-honda-civic-2-4': dict(CIVIC, key='2018-honda-civic-2-4', oilL=4.4, oilVisc='0W-20', oilFilter='PH7317', parts=[{'name': 'Plaquettes avant', 'ref': 'D1089', 'qty': 1, 'svc': 'Freins avant (plaquettes)'}], by='Saleh', updatedAt=1),
        'stock/c1__huile-0w-20': {'truck': 'c1', 'name': 'Huile 0W-20', 'ref': '', 'unit': 'L', 'qty': 20, 'min': 10},
        'stock/c1__filtre-ph7317': {'truck': 'c1', 'name': 'Filtre', 'ref': 'PH7317', 'unit': 'unité', 'qty': 3, 'min': 2},
        'stock/c1__plaquettes-avant-d1089': {'truck': 'c1', 'name': 'Plaquettes avant', 'ref': 'D1089', 'unit': 'unité', 'qty': 1, 'min': 1},
        'stock/c2__huile-5w-30': {'truck': 'c2', 'name': 'Huile 5W-30', 'ref': '', 'unit': 'L', 'qty': 30, 'min': 10},
        'clients/c1': {'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '5145550101', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'},
        'jobs/j1': {'date': iso(T), 'time': '10:00', 'durationMin': 120, 'mechanic': 'Saleh', 'truck': 'c1', 'status': 'place', 'clientId': 'c1', 'client': {'name': 'Marie Tremblay', 'phone': '5145550101'},
                    'services': ["Changement d'huile et filtre", 'Freins avant (plaquettes)'], 'vehicle': CIVIC}}
def harness(mode, ui):
    pre = 'try{sessionStorage.setItem("gm.ui",%s)}catch(e){}' % json.dumps(ui) if ui else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>{pre}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def open_page(br, width=1100, ui='full', mode=None):
    phone = width < 700
    c = br.new_context(viewport={'width': width, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA', has_touch=phone, **({'user_agent': IPHONE} if phone else {}))
    p = c.new_page(); errs = []
    p.on('pageerror', lambda e: errs.append(str(e)))
    p.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    p.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode or {'seed': seed}, ui)) if r.request.url.startswith('https://local.test/') else r.abort())
    p.goto('https://local.test/'); p.wait_for_timeout(700)
    return c, p, errs
def txt(p, sel):
    l = p.locator(sel)
    return re.sub(r'\s+', ' ', (l.first.text_content() or '').replace('\xa0', ' ').replace(' ', ' ')).strip() if l.count() else ''
def store(p, path): return p.evaluate('p => window.__store[p] || null', path)
def go_job(p, jid): p.evaluate("id => { const S = window.__garageApi.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); window.scrollTo(0, 0); }", jid); p.wait_for_timeout(400)
def go_tab(p, t): p.evaluate("t => { const S = window.__garageApi.S; S.screen = null; S.tab = t; window.__garageApi.render(); }", t); p.wait_for_timeout(400)
def qty(p, sid): return (store(p, 'stock/' + sid) or {}).get('qty')

with sync_playwright() as pw:
    br = pw.chromium.launch()
    c, p, errs = open_page(br)
    # ---------- 1. what to bring ----------
    go_job(p, 'j1')
    br_txt = txt(p, '#speccard .bring')
    check('job page: « À apporter » from the engine sheet (oil 4,4 L 0W-20, filter PH7317, front pads for the brakes)', 'Huile 0W-20 × 4,4 L' in br_txt and 'Filtre à huile PH7317 × 1 unité' in br_txt and 'Plaquettes avant D1089 × 1 unité' in br_txt, br_txt)
    check('… with what is in the truck (✓ 20 L, ✓ 3 unités, ✓ 1 unité)', '✓ 20 L en stock' in br_txt and '✓ 3 unités en stock' in br_txt and '✓ 1 unité en stock' in br_txt, br_txt)
    # ---------- 2. used parts come off the truck's stock ----------
    p.click('[data-act="done-edit"]'); p.wait_for_selector('#use-box .userow')
    check('« Travaux faits »: « Pièces utilisées · enlevées de l\'inventaire », 3 rows ready', 'enlevées de l\'inventaire' in txt(p, '#use-box') and p.locator('#use-box .userow').count() == 3, txt(p, '#use-box'))
    p.fill('[data-useq="0"]', '4,2'); p.dispatch_event('[data-useq="0"]', 'change')
    p.click('[data-act="done-save"]'); p.wait_for_timeout(800)
    j1 = store(p, 'jobs/j1')
    check('saved: job records the parts used (4,2 L oil, 1 filter, 1 pads)', [(u['name'], u['qty']) for u in j1.get('used', [])] == [('Huile 0W-20', 4.2), ('Filtre à huile', 1), ('Plaquettes avant', 1)], j1.get('used'))
    check('stock of Camion 1 lowered: oil 15,8 L, filters 2, pads 0', qty(p, 'c1__huile-0w-20') == 15.8 and qty(p, 'c1__filtre-ph7317') == 2 and qty(p, 'c1__plaquettes-avant-d1089') == 0, [qty(p, x) for x in ('c1__huile-0w-20', 'c1__filtre-ph7317', 'c1__plaquettes-avant-d1089')])
    check('the other truck is untouched', qty(p, 'c2__huile-5w-30') == 30)
    check('job page shows « Pièces utilisées : Huile 0W-20 × 4,2 L, … »', 'Pièces utilisées : Huile 0W-20 × 4,2 L' in txt(p, 'main'))
    p.click('[data-act="done-edit"]'); p.wait_for_selector('#use-box .userow'); p.wait_for_timeout(200)
    check('opening it again shows what was recorded (4,2)', p.input_value('[data-useq="0"]') == '4,2')
    p.click('[data-act="done-save"]'); p.wait_for_timeout(800)
    check('saving again without change takes nothing more', qty(p, 'c1__huile-0w-20') == 15.8 and qty(p, 'c1__filtre-ph7317') == 2)
    p.click('[data-act="done-edit"]'); p.wait_for_selector('#use-box .userow')
    p.fill('[data-useq="1"]', '2'); p.dispatch_event('[data-useq="1"]', 'change'); p.click('[data-act="done-save"]'); p.wait_for_timeout(800)
    check('2 filters instead of 1: only the difference comes off (2 → 1)', qty(p, 'c1__filtre-ph7317') == 1, qty(p, 'c1__filtre-ph7317'))
    p.click('[data-act="done-edit"]'); p.wait_for_selector('#use-box .userow')
    p.click('#svc-picked button[aria-label*="Freins"]'); p.wait_for_timeout(300)
    check('brakes removed from the work: the pads row goes away', p.locator('#use-box .userow').count() == 2 and 'Plaquettes' not in txt(p, '#use-box'), txt(p, '#use-box'))
    p.click('[data-act="done-save"]'); p.wait_for_timeout(800)
    check('… and the pads go back into the truck (0 → 1); oil/filter follow the new list', qty(p, 'c1__plaquettes-avant-d1089') == 1 and qty(p, 'c1__filtre-ph7317') == 2 and qty(p, 'c1__huile-0w-20') == 15.6, [qty(p, x) for x in ('c1__huile-0w-20', 'c1__filtre-ph7317', 'c1__plaquettes-avant-d1089')])
    # ---------- 3. stock screen ----------
    p.evaluate("() => { const S = window.__garageApi.S; S.screen = null; }")
    p.evaluate("window.__store['stock/c1__filtre-ph7317'] && 0"); go_tab(p, 'stock')
    check('« Inventaire »: one list for the garage (the 4 articles of both trucks)', 'Inventaire' in txt(p, '#top') and p.locator('.stkrow').count() == 4 and 'Huile 5W-30' in txt(p, 'main') and 'Camion 1' not in txt(p, 'main'), txt(p, 'main')[:300])
    p.click('.top-in [data-act="stk-new"]'); p.wait_for_selector('#stk-name')
    p.fill('#stk-name', 'Lave-glace'); p.select_option('#stk-unit', 'L'); p.fill('#stk-q0', '8'); p.fill('#stk-min', '4'); p.click('[data-act="stk-save"]'); p.wait_for_timeout(600)
    lg = store(p, 'stock/lave-glace') or {}
    check('« + Article »: Lave-glace, 8 L, racheter sous 4, in the inventory (no truck)', lg.get('qty') == 8 and lg.get('unit') == 'L' and lg.get('min') == 4 and 'truck' not in lg, lg)
    p.click('[data-act="stk-open"][data-id="lave-glace"]'); p.wait_for_selector('#stk-n')
    p.fill('#stk-n', '12'); p.click('[data-act="stk-save"]'); p.wait_for_timeout(500)
    check('Entrée +12 → 20 L', qty(p, 'lave-glace') == 20)
    p.click('[data-act="stk-open"][data-id="lave-glace"]'); p.wait_for_selector('#stk-n'); p.click('[data-act="stk-mode"][data-v="out"]'); p.fill('#stk-n', '3'); p.click('[data-act="stk-save"]'); p.wait_for_timeout(500)
    check('Sortie −3 → 17 L', qty(p, 'lave-glace') == 17)
    p.click('[data-act="stk-open"][data-id="lave-glace"]'); p.wait_for_selector('#stk-n'); p.click('[data-act="stk-mode"][data-v="set"]')
    check('« Compter » changes the label', 'comptée' in txt(p, '#stk-nl'))
    p.fill('#stk-n', '3'); p.click('[data-act="stk-save"]'); p.wait_for_timeout(500)
    check('Compter = 3 → 3 L, shown « À racheter » (under 4)', qty(p, 'lave-glace') == 3 and 'À racheter' in txt(p, '[data-id="lave-glace"]'), txt(p, '[data-id="lave-glace"]'))
    check('banner lists what to buy again', 'à racheter' in txt(p, '.banner.warn') and 'Lave-glace' in txt(p, '.banner.warn'), txt(p, '.banner.warn'))
    p.click('[data-act="stk-new"] >> nth=0'); p.wait_for_selector('#stk-name'); p.fill('#stk-name', 'Lave-glace'); p.select_option('#stk-unit', 'L'); p.fill('#stk-q0', '1'); p.click('[data-act="stk-save"]'); p.wait_for_timeout(300)
    check('same article twice: refused', 'déjà à l\'inventaire' in txt(p, '#stk-err'))
    p.click('.sheet-head [data-act="sheet-close"]'); p.wait_for_timeout(200)
    p.click('[data-act="stk-open"][data-id="lave-glace"]'); p.wait_for_selector('[data-act="stk-del"]'); p.click('[data-act="stk-del"]'); p.wait_for_timeout(100); p.click('[data-act="stk-del"]'); p.wait_for_timeout(500)
    check('« Retirer » (two taps) removes the article', store(p, 'stock/lave-glace') is None)
    go_tab(p, 'accueil')
    check('dashboard: « article(s) à racheter » with a link to the stock', 'à racheter' in txt(p, 'main') and p.locator('main a[href="#stock"]').count() >= 1)
    # ---------- 4. engine sheet: its parts ----------
    go_job(p, 'j1'); p.click('#speccard [data-act="spec-edit"]'); p.wait_for_selector('#pp-rows')
    check('engine sheet editor shows its parts (1 row)', p.locator('#pp-rows .pprow').count() == 1 and p.input_value('#pp-rows .pprow .pp-ref') == 'D1089')
    p.click('[data-act="pp-add"]'); row = p.locator('#pp-rows .pprow').nth(1)
    row.locator('.pp-name').fill('Bougies'); row.locator('.pp-ref').fill('ILZKR7B11'); row.locator('.pp-qty').fill('4')
    p.click('#sp-save'); p.wait_for_timeout(600)
    sp = store(p, 'specs/2018-honda-civic-2-4') or {}
    check('saved: 2 parts (pads for the brakes, 4 plugs for every job)', [(x['name'], x['qty'], x['svc']) for x in sp.get('parts', [])] == [('Plaquettes avant', 1, 'Freins avant (plaquettes)'), ('Bougies', 4, '')], sp.get('parts'))
    check('« À apporter » now has the plugs (not in stock)', 'Bougies ILZKR7B11 × 4 unités' in txt(p, '#speccard .bring') and 'pas à l\'inventaire' in txt(p, '#speccard .bring'), txt(p, '#speccard .bring'))
    # ---------- 5. the waiver (no more photos), extra work in this version ----------
    check('no photo buttons anymore (single-page version)', p.locator('#pin-av, #pin-ap').count() == 0 and p.locator('#wv-sect').count() == 1)
    p.click('#wv-sect [data-act="wv-open"]'); p.wait_for_selector('#sigpad')
    bb = p.locator('#sigpad').bounding_box(); p.mouse.move(bb['x'] + 40, bb['y'] + 100); p.mouse.down(); p.mouse.move(bb['x'] + 220, bb['y'] + 60); p.mouse.move(bb['x'] + 300, bb['y'] + 120); p.mouse.up()
    p.click('#sig-save'); p.wait_for_timeout(800)
    check('waiver signed', ((store(p, 'jobs/j1') or {}).get('waiver') or {}).get('name') == 'Marie Tremblay')
    p.click('#xp-sect [data-act="xp-new"]'); p.wait_for_selector('#xp-desc'); p.fill('#xp-desc', 'Courroie'); p.fill('#xp-price', '160'); p.click('[data-act="xp-save"]'); p.wait_for_timeout(500)
    check('no « texto » button here (no server): only signature or « il a dit oui / non »', p.locator('[data-act="xp-send"]').count() == 0 and p.locator('[data-act="xp-sign"]').count() == 1)
    p.click('[data-act="xp-yes"]'); p.wait_for_timeout(500)
    check('« Il a dit oui » → accepted', ((store(p, 'jobs/j1') or {}).get('extras') or [{}])[0].get('status') == 'accepte')
    check('no invoice-sending button here', p.locator('[data-act="inv-send"]').count() == 0)
    check('no JS errors (desktop)', not errs, errs)
    c.close()
    # ---------- 6. phone: Plus → stock ----------
    c, p, errs = open_page(br, 390, None)
    go_tab(p, 'plus')
    check('phone « Plus »: « Inventaire · 1 article à racheter »', 'Inventaire' in txt(p, 'main') and '1 article à racheter' in txt(p, 'main'), txt(p, 'main')[:300])
    p.click('a[href="#stock"]'); p.wait_for_timeout(500)
    check('phone stock screen opens, « + Article » button, no sideways scroll', 'Huile 0W-20' in txt(p, 'main') and p.locator('main [data-act="stk-new"]').count() == 1 and p.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
    go_job(p, 'j1'); p.click('#veh-fold summary'); p.wait_for_timeout(200)
    check('phone job: « À apporter » in the vehicle fold', 'À apporter pour cette job' in txt(p, '#veh-fold'))
    check('no JS errors (phone)', not errs, errs)
    c.close()
    # ---------- 7. read-only viewer ----------
    c, p, errs = open_page(br, mode={'seed': seed, 'readOnly': True})
    p.evaluate("() => { window.__garageApi.S.canWrite = false; }"); go_tab(p, 'stock')
    check('read-only: stock visible, no « + Article », rows not clickable', 'Huile 0W-20' in txt(p, 'main') and p.locator('[data-act="stk-new"]').count() == 0 and p.locator('.stkrow[disabled]').count() >= 3)
    go_job(p, 'j1')
    check('read-only: no photo / signature / proposal buttons', p.locator('[data-act="sig-open"], [data-act="wv-open"]').count() == 0 and p.locator('[data-act="xp-new"]').count() == 0 and p.locator('#pin-av').count() == 0)
    c.close(); br.close()
n = sum(1 for _, ok in results if ok)
print(f'\n{n}/{len(results)} passed'); sys.exit(0 if n == len(results) else 1)
