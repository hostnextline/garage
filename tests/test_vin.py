"""VIN: live camera scan (fake camera playing a real Code 39 barcode), photo, typing; free decoding; the garage's engine sheet (oil etc.)."""
import json, os, datetime, re, sys
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
V = os.path.join(SC, 'vin')
PAGE = open('/home/claude/garage/carnet.html', encoding='utf8').read()
MOCK = open(os.path.join(SC, 'mock.js'), encoding='utf8').read()
ZX = open(os.path.join(SC, 'zxinglib/node_modules/@zxing/library/umd/index.min.js'), encoding='utf8').read()
ZX_URL = 'https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js'
RESET = 'html{color-scheme:light}:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0;font:14px system-ui}img{max-width:100%}[hidden]{display:none!important}'
T = datetime.date.today(); iso = lambda d: d.isoformat()
W = T + datetime.timedelta(days=3)
while W.weekday() != 2: W += datetime.timedelta(days=1)
CIVIC, RAV4, FORD, MAZDA = '2HGFC2F58JH512345', '2T3W1RFV6LW012345', '1FTFW1E57MFA12345', 'JM1BPACL5M1301234'
VPIC = {CIVIC: {'ModelYear': '2018', 'Make': 'HONDA', 'Model': 'Civic', 'Trim': 'LX', 'Series': '', 'DisplacementL': '2.0', 'EngineCylinders': '4', 'FuelTypePrimary': 'Gasoline', 'DriveType': 'FWD/Front-Wheel Drive', 'ElectrificationLevel': '', 'ErrorCode': '0'},
        RAV4: {'ModelYear': '2020', 'Make': 'TOYOTA', 'Model': 'RAV4', 'Trim': 'XLE', 'Series': 'AXAA54L', 'DisplacementL': '2.487500', 'EngineCylinders': '4', 'FuelTypePrimary': 'Gasoline', 'DriveType': 'AWD/All-Wheel Drive', 'ElectrificationLevel': '', 'ErrorCode': '0'}}
def job(t, veh, name='Marie Tremblay', st='planifie'):
    return {'date': iso(W), 'time': t, 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'status': st, 'clientId': 'c1', 'client': {'name': name, 'phone': '5145550101', 'address': '4520 rue Saint-Denis, Montréal'}, 'services': ["Changement d'huile et filtre"], 'vehicle': veh}
seed = {'config/main': {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Saleh', 'Ali'], 'rate': 120, 'taxesOn': True, 'prefix': 'F-', 'startNo': 1, 'services': [{'name': "Changement d'huile et filtre", 'price': 89.95}],
                        'trucks': [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': False, 'mech': ''}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}]},
        'clients/c1': {'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '5145550101', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3'},
        'jobs/j1': job('08:00', {'year': '2018', 'make': 'Honda', 'model': 'Civic', 'plate': 'ABC123', 'km': '142000'}),
        'jobs/j2': job('09:30', {'year': '2018', 'make': 'Honda', 'model': 'Civic', 'displL': 2, 'cyl': 4}),
        'jobs/j3': job('11:00', {'year': '2019', 'make': 'Honda', 'model': 'Civic', 'displL': 2, 'cyl': 4}),
        'jobs/j4': job('13:00', {'plate': 'XYZ789'}),
        'jobs/j5': job('14:30', {}),
        'jobs/j6': job('16:00', {'year': '2017', 'make': 'Ford', 'model': 'F-150'}, st='annule')}
def harness(mode, ui):
    pre = 'try{sessionStorage.setItem("gm.ui",%s)}catch(e){}' % json.dumps(ui) if ui else ''
    return ('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f'<style>{RESET}</style><script>{pre}window.__MOCK={json.dumps(mode)};</script><script>{MOCK}</script></head><body>{PAGE}</body></html>')
STREAMS = """(() => { window.__streams = []; window.__gum = 0; const md = navigator.mediaDevices; if (!md || !md.getUserMedia) return; const g = md.getUserMedia.bind(md);
  md.getUserMedia = c => { window.__gum++; if (window.__denyCam) return Promise.reject(new DOMException('denied', 'NotAllowedError')); return g(c).then(s => { window.__streams.push(s); return s; }); }; })();"""
FAKE_BD = """window.BarcodeDetector = class { constructor(o){ window.__bdFormats = o && o.formats; this.n = 0; } detect(){ this.n++; window.__bdCalls = (window.__bdCalls || 0) + 1; return Promise.resolve(this.n < 4 ? [] : [{rawValue: 'I""" + RAV4 + """'}]); } };"""
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def open_page(br, width=1100, ui='full', vpic='ok', zx='ok', init=None, mode=None):
    phone = width < 700
    ctx = br.new_context(viewport={'width': width, 'height': 900}, timezone_id='America/Toronto', locale='fr-CA', has_touch=phone, permissions=['camera'],
                         **({'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'} if phone else {}))
    pg = ctx.new_page(); errs = []; net = {'zx': 0, 'vpic': []}
    pg.add_init_script(STREAMS)
    if init: pg.add_init_script(init)
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    def route(r):
        u = r.request.url
        if u.startswith('https://local.test/'): return r.fulfill(status=200, content_type='text/html; charset=utf-8', body=harness(mode or {'seed': seed}, ui))
        if u == ZX_URL:
            net['zx'] += 1
            return r.fulfill(status=200, content_type='application/javascript', body=ZX) if zx == 'ok' else r.abort()
        m = re.match(r'https://vpic\.nhtsa\.dot\.gov/api/vehicles/DecodeVinValues/([A-Z0-9]+)\?format=json$', u)
        if m:
            net['vpic'].append(m.group(1))
            if vpic != 'ok': return r.abort()
            res = VPIC.get(m.group(1)) or {'ModelYear': '', 'Make': '', 'Model': '', 'ErrorCode': '8', 'ErrorText': '8 - No detailed data available currently'}
            return r.fulfill(status=200, content_type='application/json', headers={'Access-Control-Allow-Origin': '*'}, body=json.dumps({'Count': 1, 'Results': [dict(VIN=m.group(1), **res)]}))
        return r.abort()
    pg.route('**/*', route)
    pg.goto('https://local.test/'); pg.wait_for_timeout(700)
    return ctx, pg, errs, net
def txt(pg, sel): return re.sub(r'\s+', ' ', (pg.locator(sel).first.text_content() or '').replace('\xa0', ' ').replace(' ', ' ')).strip()
def store(pg, path): return pg.evaluate('p => window.__store[p] || null', path)
def wait(pg, ms=300): pg.wait_for_timeout(ms)
def go_job(pg, jid): pg.evaluate("id => { const S = window.__garageApi.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = id; window.__garageApi.render(); window.scrollTo(0, 0); }", jid); wait(pg)
def wait_for(pg, js, ms=12000):
    try: pg.wait_for_function(js, timeout=ms); return True
    except Exception: return False
def cams_live(pg): return pg.evaluate("window.__streams.reduce((n, s) => n + s.getTracks().filter(t => t.readyState === 'live').length, 0)")
def launch(p, video):
    return p.chromium.launch(args=['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', '--use-file-for-fake-video-capture=' + os.path.join(V, video)])

with sync_playwright() as p:
    br = launch(p, 'vin_civic.y4m')
    # ================= A. job page: live camera scan → decode → put on the job =================
    ctx, pg, errs, net = open_page(br)
    go_job(pg, 'j1')
    check('A1. job page: « Scanner le VIN » in the Véhicule section', pg.locator('.sect-head [data-act="scan-job"]').count() == 1)
    check('A2. engine sheet card: « Pas encore dans la fiche du garage »', 'Pas encore dans la fiche du garage' in txt(pg, '#speccard') and pg.locator('#speccard [data-act="spec-edit"]').count() == 1, txt(pg, '#speccard'))
    pg.click('[data-act="scan-job"]'); wait(pg, 200)
    check('A3. scanner sheet opens « Scanner le VIN »', pg.locator('#sheet').is_visible() and 'Scanner le VIN' in txt(pg, '.sheet-head'))
    ok = wait_for(pg, "document.querySelector('#scan-body .vehsum')")
    check('A4. the live camera reads the door-sticker barcode by itself (ZXing, no click)', ok and net['zx'] == 1 and pg.evaluate('window.__gum') >= 1, (net, txt(pg, '#scan-body')))
    body = txt(pg, '#scan-body')
    check('A5. decoded: VIN ✓, « 2018 Honda Civic LX », « 2,0 L 4 cyl. · Traction avant »', CIVIC in body and '✓' in body and '2018 Honda Civic LX' in body and '2,0 L 4 cyl. · Traction avant' in body, body)
    check('A6. oil not known yet: says so', 'Huile : pas encore dans la fiche du garage' in body, body)
    check('A7. camera turned off as soon as the VIN is read', cams_live(pg) == 0 and len(net['vpic']) == 1 and net['vpic'][0] == CIVIC, (cams_live(pg), net['vpic']))
    pg.click('[data-act="scan-use"]'); wait(pg, 400)
    vj = (store(pg, 'jobs/j1') or {}).get('vehicle') or {}
    check('A8. « Mettre sur la job » saves VIN + year/make/model/trim/engine/drive, keeps plate and km',
          vj.get('vin') == CIVIC and vj.get('year') == '2018' and vj.get('make') == 'Honda' and vj.get('model') == 'Civic' and vj.get('trim') == 'LX' and vj.get('displL') == 2 and vj.get('cyl') == 4
          and vj.get('fuel') == 'Essence' and vj.get('drive') == 'Traction avant' and vj.get('engine') == '2,0 L 4 cyl.' and vj.get('plate') == 'ABC123' and vj.get('km') == '142000', vj)
    check('A9. sheet closed, toast « Véhicule mis à jour », page shows the engine', not pg.locator('#sheet').is_visible() and 'Véhicule mis à jour' in txt(pg, '#toast') and 'LX · 2,0 L 4 cyl. · Traction avant' in txt(pg, '.tk-veh'), txt(pg, '.tk-veh'))
    # ---- engine sheet: filled once ----
    pg.click('#speccard [data-act="spec-edit"]'); wait(pg, 200)
    check('A10. engine sheet form: says it is for every car with this engine', 'toutes les autos avec ce moteur (2018 Honda Civic 2,0 L 4 cyl.)' in txt(pg, '#specform'), txt(pg, '#specform')[:200])
    pg.fill('#sp-oilL', '44'); pg.click('#sp-save'); wait(pg, 200)
    check('A11. 44 litres refused (« en litres (ex. 4,4) »), nothing saved', "La quantité d'huile doit être en litres" in txt(pg, '#toast') and not any(k.startswith('specs/') for k in pg.evaluate('Object.keys(window.__store)')))
    pg.fill('#sp-oilL', '4,4'); pg.click('[data-act="sp-visc"][data-v="0W-20"]'); pg.fill('#sp-oilFilter', 'PH7317'); pg.fill('#sp-drainTorque', '40 N·m'); pg.fill('#sp-tires', '215/55R16'); pg.fill('#sp-pressure', '32 psi')
    check('A12. viscosity chip fills the field', pg.input_value('#sp-oilVisc') == '0W-20')
    pg.click('#sp-save'); wait(pg, 400)
    keys = [k for k in pg.evaluate('Object.keys(window.__store)') if k.startswith('specs/')]
    sp = store(pg, keys[0]) if keys else {}
    check('A13. saved once as specs/2018-honda-civic-2-4: 4.4 L, 0W-20, PH7317, tires, pressure', keys == ['specs/2018-honda-civic-2-4'] and sp.get('oilL') == 4.4 and sp.get('oilVisc') == '0W-20' and sp.get('oilFilter') == 'PH7317'
          and sp.get('tires') == '215/55R16' and sp.get('pressure') == '32 psi' and sp.get('engine') == '2,0 L 4 cyl.' and sp.get('updatedAt'), (keys, sp))
    check('A14. job page now shows « Huile : 4,4 L · 0W-20 · filtre PH7317 » and the other lines', 'Huile : 4,4 L · 0W-20 · filtre PH7317' in txt(pg, '#speccard') and '215/55R16' in txt(pg, '#speccard') and 'Modifier la fiche' in txt(pg, '#speccard'), txt(pg, '#speccard'))
    # ---- reuse: same engine, same year → already filled; other year → suggested « à confirmer » ----
    go_job(pg, 'j2')
    check('A15. another 2018 Civic 2.0: oil already there, nothing to type', 'Huile : 4,4 L · 0W-20' in txt(pg, '#speccard') and 'à confirmer' not in txt(pg, '#speccard'), txt(pg, '#speccard'))
    go_job(pg, 'j3')
    check('A16. a 2019 Civic 2.0: oil from the 2018 « à confirmer »', 'Huile : 4,4 L' in txt(pg, '#speccard') and "D'après une 2018 (même moteur) : à confirmer" in txt(pg, '#speccard') and 'Confirmer pour ce moteur' in txt(pg, '#speccard'), txt(pg, '#speccard'))
    pg.click('#speccard [data-act="spec-edit"]'); wait(pg, 200)
    check('A17. confirming opens the sheet already filled from the 2018', pg.input_value('#sp-oilL') == '4,4' and pg.input_value('#sp-oilVisc') == '0W-20' and "Rempli d'après une 2018" in txt(pg, '#specform'))
    pg.click('#sp-save'); wait(pg, 400)
    check('A18. saved for the 2019 too, no longer « à confirmer »', (store(pg, 'specs/2019-honda-civic-2-4') or {}).get('oilL') == 4.4 and 'à confirmer' not in txt(pg, '#speccard'), txt(pg, '#speccard'))
    go_job(pg, 'j6')
    check('A24. cancelled job: no scan button', pg.locator('[data-act="scan-job"]').count() == 0)
    # ================= B. booking form: inline scanner, typed VIN =================
    pg.evaluate("() => { const S = window.__garageApi.S; S.screen = null; S.tab = 'agenda'; S.day = '%s'; window.__garageApi.render(); }" % iso(W)); wait(pg)
    go_job(pg, 'j4'); pg.click('[data-act="edit"]'); wait(pg, 400)
    check('B1. booking form: « Scanner le VIN » next to the VIN field', pg.locator('#jobform [data-act="scan-vin"]').count() == 1)
    pg.click('#jobform [data-act="scan-vin"]'); ok = wait_for(pg, "document.getElementById('f-make') && document.getElementById('f-make').value === 'Honda'")
    check('B2. live scan fills VIN, year, make, model in the form', ok and pg.input_value('#f-vin') == CIVIC and pg.input_value('#f-year') == '2018' and pg.input_value('#f-model') == 'Civic', [pg.input_value(s) for s in ('#f-vin', '#f-year', '#f-make', '#f-model')])
    check('B3. under the VIN: the car, the engine and the oil from the garage sheet', 'Huile : 4,4 L · 0W-20 · filtre PH7317' in txt(pg, '#specmsg') and '2,0 L 4 cyl.' in txt(pg, '#specmsg') and pg.locator('#scanpanel').is_hidden() and cams_live(pg) == 0, txt(pg, '#specmsg'))
    pg.click('#f-save'); wait(pg, 500)
    vj = (store(pg, 'jobs/j4') or {}).get('vehicle') or {}
    check('B4. saved booking keeps the decoded engine + the plate', vj.get('vin') == CIVIC and vj.get('engine') == '2,0 L 4 cyl.' and vj.get('drive') == 'Traction avant' and vj.get('plate') == 'XYZ789', vj)
    go_job(pg, 'j4'); pg.click('[data-act="edit"]'); wait(pg, 400); pg.fill('#f-notes', 'Client préfère le matin'); pg.click('#f-save'); wait(pg, 500)
    vj = (store(pg, 'jobs/j4') or {}).get('vehicle') or {}
    check('B5. editing the booking later does not lose the engine details', vj.get('engine') == '2,0 L 4 cyl.' and vj.get('trim') == 'LX' and (store(pg, 'jobs/j4') or {}).get('notes') == 'Client préfère le matin', vj)
    go_job(pg, 'j5'); pg.click('[data-act="edit"]'); wait(pg, 400)
    pg.fill('#f-vin', RAV4.lower()); ok = wait_for(pg, "document.getElementById('f-model').value === 'RAV4'", 5000)
    check('B6. typing a good 17-character VIN decodes by itself (2020 Toyota RAV4)', ok and pg.input_value('#f-year') == '2020' and pg.input_value('#f-make') == 'Toyota' and 'Intégrale' in txt(pg, '#specmsg'), txt(pg, '#specmsg'))
    pg.fill('#f-vin', ''); pg.fill('#f-make', 'Toyota'); pg.fill('#f-model', 'Rav 4 hybride'); pg.fill('#f-year', '')
    pg.fill('#f-vin', RAV4); wait_for(pg, "/RAV4/.test(document.getElementById('specmsg').textContent)", 5000)
    check('B7. typed VIN never overwrites what the person already wrote (only empty fields)', pg.input_value('#f-model') == 'Rav 4 hybride' and pg.input_value('#f-year') == '2020', [pg.input_value('#f-year'), pg.input_value('#f-model')])
    pg.click('#f-save'); wait(pg, 500)
    vj = (store(pg, 'jobs/j5') or {}).get('vehicle') or {}
    check('B8. model changed by hand → engine details from the scan not saved on it', vj.get('model') == 'Rav 4 hybride' and 'engine' not in vj, vj)
    check('A/B. no JS errors', not errs, errs)
    ctx.close()
    # ================= C. vehicle base unreachable / reader blocked / camera refused =================
    ctx, pg, errs, net = open_page(br, vpic='down')
    go_job(pg, 'j5'); pg.click('[data-act="edit"]'); wait(pg, 400)
    pg.fill('#f-vin', MAZDA); ok = wait_for(pg, "document.getElementById('f-make').value === 'Mazda'", 5000)
    check('C1. NHTSA base down: make from the VIN (Mazda), year left to the « Mettre … comme année » button', ok and pg.input_value('#f-year') == '' and 'comme année' in txt(pg, '#vinmsg') and 'pas joignable' in txt(pg, '#specmsg'), (txt(pg, '#vinmsg'), txt(pg, '#specmsg')))
    check('C2. no JS errors', not errs, errs); ctx.close()
    ctx, pg, errs, net = open_page(br, zx='down')
    go_job(pg, 'j5'); pg.click('[data-act="scan-job"]'); ok = wait_for(pg, "/pas pu se charger/.test(document.querySelector('#scan-msg').textContent)", 6000)
    check('C3. barcode reader cannot load: says so, typing still works', ok, txt(pg, '#scan-msg'))
    pg.click('[data-act="scan-type"]'); pg.fill('#scan-in', CIVIC); pg.click('[data-act="scan-typed"]'); ok = wait_for(pg, "document.querySelector('#scan-body .vehsum')", 5000)
    check('C4. … and the typed VIN decodes', ok and '2018 Honda Civic LX' in txt(pg, '#scan-body')); ctx.close()
    # ---- camera refused: photo and typing ----
    ctx, pg, errs, net = open_page(br, init='window.__denyCam = true;')
    go_job(pg, 'j5'); pg.click('[data-act="scan-job"]'); ok = wait_for(pg, "/caméra est bloquée/.test(document.querySelector('#scan-msg').textContent)", 6000)
    check('C5. camera refused: « La caméra est bloquée : permets-la, ou prends une photo / tape le VIN »', ok, txt(pg, '#scan-msg'))
    check('C5b. the sheet has the camera view and the 2 other ways (photo, typing)', pg.locator('#sheet #scan-v').count() == 1 and 'Prendre une photo' in txt(pg, '#sheet') and 'Taper le VIN' in txt(pg, '#sheet'))
    pg.set_input_files('#scan-file', os.path.join(V, 'blank.png')); ok = wait_for(pg, "/Pas de code-barres lisible/.test(document.querySelector('#scan-msg').textContent)", 15000)
    check('A19. photo without a barcode: « Pas de code-barres lisible… tape le VIN »', ok, txt(pg, '#scan-msg'))
    pg.set_input_files('#scan-file', os.path.join(V, 'vin_rav4_I.png')); ok = wait_for(pg, "document.querySelector('#scan-body .vehsum')", 15000)
    body = txt(pg, '#scan-body')
    check('A20. photo of the sticker « I2T3W1… »: the leading I is dropped, 2020 Toyota RAV4 XLE, 2,5 L, Intégrale', ok and RAV4 in body and '2020 Toyota RAV4 XLE' in body and '2,5 L 4 cyl. · Intégrale' in body, body)
    pg.click('[data-act="scan-again"]'); wait(pg, 300)
    pg.click('[data-act="scan-type"]'); pg.fill('#scan-in', 'ABC123'); pg.click('[data-act="scan-typed"]'); wait(pg, 100)
    check('A21. « Taper le VIN »: a wrong VIN gets a clear message', '17 lettres et chiffres' in txt(pg, '#scan-msg'), txt(pg, '#scan-msg'))
    pg.fill('#scan-in', FORD.lower()); pg.click('[data-act="scan-typed"]'); ok = wait_for(pg, "document.querySelector('#scan-body .vehsum')", 5000)
    body = txt(pg, '#scan-body')
    check('A22. typed VIN not in the base: make from the VIN (Ford), asks to complete the model', ok and 'Ford' in body and "Ce VIN n'est pas dans la base" in body, body)
    pg.click('.sheet-head [data-act="sheet-close"]'); wait(pg, 200)
    check('A23. closing without « Mettre sur la job » changes nothing', (store(pg, 'jobs/j5') or {}).get('vehicle') == {})
    check('C6. no JS errors', not errs, errs); ctx.close()
    # ================= D. phones with a built-in barcode reader (Android Chrome): no download =================
    ctx, pg, errs, net = open_page(br, 390, None, init=FAKE_BD)
    go_job(pg, 'j5')
    check('D1. phone job page: « Véhicule et fiche technique · VIN à scanner » (folded like the other details)', 'VIN à scanner' in txt(pg, '#veh-fold summary') and pg.locator('#veh-fold[open]').count() == 0)
    pg.click('#veh-fold summary'); wait(pg, 200)
    check('D1b. opened: « Scanner le VIN » button, no sideways scroll', pg.locator('#veh-fold [data-act="scan-job"]').is_visible() and pg.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
    pg.click('#veh-fold [data-act="scan-job"]'); ok = wait_for(pg, "document.querySelector('#scan-body .vehsum')", 8000)
    check('D2. built-in reader used (Code 39 + DataMatrix asked), ZXing never downloaded', ok and net['zx'] == 0 and 'code_39' in (pg.evaluate('window.__bdFormats') or []) and 'data_matrix' in (pg.evaluate('window.__bdFormats') or []) and pg.evaluate('window.__bdCalls') >= 4, (net, pg.evaluate('window.__bdFormats')))
    check('D3. the sticker\'s leading I removed → RAV4 decoded; camera off', '2020 Toyota RAV4 XLE' in txt(pg, '#scan-body') and cams_live(pg) == 0, txt(pg, '#scan-body'))
    pg.click('[data-act="scan-use"]'); wait(pg, 400)
    check('D4. phone: saved on the job', ((store(pg, 'jobs/j5') or {}).get('vehicle') or {}).get('model') == 'RAV4')
    ctx.close()
    # ================= E. phone with the oil known; read-only =================
    seed2 = dict(seed); seed2['specs/2018-honda-civic-2-4'] = {'year': '2018', 'make': 'Honda', 'model': 'Civic', 'displL': 2, 'cyl': 4, 'oilL': 4.4, 'oilVisc': '0W-20', 'oilFilter': 'PH7317', 'by': 'Saleh', 'updatedAt': 1761800000000}
    ctx, pg, errs, net = open_page(br, 390, None, mode={'seed': seed2})
    go_job(pg, 'j2')
    check('E1. phone job header: oil line right under the car', 'Huile : 4,4 L · 0W-20 · filtre PH7317' in txt(pg, '.pj-what .pj-oil'), txt(pg, '.pj-what'))
    pg.click('#veh-fold summary'); wait(pg, 200)
    check('E2. phone fold: engine sheet with « Confirmé par Saleh »', 'Confirmé par Saleh' in txt(pg, '#veh-fold') and 'Rescanner' not in txt(pg, '#veh-fold') and 'Scanner le VIN' in txt(pg, '#veh-fold'), txt(pg, '#veh-fold')[:300])
    check('E3. no horizontal scroll on the phone', pg.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'))
    ctx.close()
    ctx, pg, errs, net = open_page(br, 1100, 'full', mode={'seed': seed2, 'readOnly': True})
    pg.evaluate("() => { window.__garageApi.S.canWrite = false; }"); go_job(pg, 'j2')
    check('E4. read-only: oil visible, no scan button, no « Modifier la fiche »', 'Huile : 4,4 L' in txt(pg, '#speccard') and pg.locator('[data-act="scan-job"]').count() == 0 and pg.locator('[data-act="spec-edit"]').count() == 0)
    check('E5. no JS errors', not errs, errs); ctx.close()
    br.close()
    # ================= F. a code that is not a VIN =================
    br = launch(p, 'not_vin.y4m')
    ctx, pg, errs, net = open_page(br)
    go_job(pg, 'j5'); pg.click('[data-act="scan-job"]'); ok = wait_for(pg, "/pas un VIN/.test(document.querySelector('#scan-msg').textContent)", 15000)
    check('F1. another barcode (not a VIN): « Ce code n\'est pas un VIN », camera keeps looking', ok and cams_live(pg) >= 1 and pg.locator('#scan-body .vehsum').count() == 0, txt(pg, '#scan-msg'))
    pg.keyboard.press('Escape'); wait(pg, 300)
    if pg.locator('#sheet').is_visible(): pg.click('.sheet-head [data-act="sheet-close"]'); wait(pg, 200)
    check('F2. closing → camera off', cams_live(pg) == 0)
    check('F3. no JS errors', not errs, errs); ctx.close(); br.close()
n = sum(1 for _, ok in results if ok)
print(f'\n{n}/{len(results)} passed'); sys.exit(0 if n == len(results) else 1)
