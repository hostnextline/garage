import json, os, time, urllib.parse
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/web/index.html', encoding='utf8').read()
JSPDF = os.path.join(SC, 'deps/node_modules/jspdf/dist/jspdf.umd.min.js')
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)) if detail and not cond else ''))

# documented TomTom Search API v2 answer shape (results[] with address + position)
def tt_res(num, street, city, pc, lat, lon, kind='Point Address'):
    a = {'streetName': street, 'municipality': city, 'countrySubdivision': 'QC', 'postalCode': pc[:3], 'extendedPostalCode': pc, 'countryCode': 'CA', 'country': 'Canada', 'freeformAddress': (f'{num} ' if num else '') + f'{street}, {city} QC {pc}'}
    if num: a['streetNumber'] = num
    return {'type': kind, 'id': 'x', 'score': 0.99, 'address': a, 'position': {'lat': lat, 'lon': lon}}
TT_OK = {'summary': {'query': 'x', 'queryTime': 80, 'numResults': 1}, 'results': [tt_res('1200', 'Rue Essai-Sud', 'Montréal', 'H4P 2B5', 45.501, -73.651)]}
# Photon (OpenStreetMap) answer shape: GeoJSON features with housenumber/street/city/postcode/state/countrycode
def ph(num, street, city, pc, lon, lat, typ='house'):
    p = {'osm_key': 'place' if num else 'highway', 'osm_value': 'house' if num else 'residential', 'type': typ, 'street': street if num else None, 'name': None if num else street, 'housenumber': num or None, 'city': city, 'postcode': pc, 'state': 'Québec', 'country': 'Canada', 'countrycode': 'CA'}
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [lon, lat]}, 'properties': {k: v for k, v in p.items() if v}}
PH_HOUSE = {'type': 'FeatureCollection', 'features': [ph('1200', 'Rue Essai-Sud', 'Montréal', 'H4P 2B5', -73.651, 45.501), ph('1200', 'Rue Essai', 'Ottawa', 'K1A 0B1', -75.7, 45.42) | {'properties': {'housenumber': '1200', 'street': 'Rue Essai', 'city': 'Ottawa', 'postcode': 'K1A 0B1', 'state': 'Ontario', 'countrycode': 'CA', 'type': 'house'}}, ph('1200', 'Rue Ailleurs', 'Plattsburgh', '12901', -73.45, 44.7) | {'properties': {'housenumber': '1200', 'street': 'Rue Ailleurs', 'city': 'Plattsburgh', 'state': 'New York', 'countrycode': 'US', 'type': 'house'}}]}
PH_NOPC = {'type': 'FeatureCollection', 'features': [ph('55', 'Rue Sans-Code', 'Montréal', '', -73.6, 45.5)]}
PH_STREET = {'type': 'FeatureCollection', 'features': [ph('', 'Rue Essai-Sud', 'Montréal', 'H4P 2B1', -73.65, 45.50, 'street'), ph('', 'Rue Essai-Sud', 'Montréal', 'H4P 2B9', -73.652, 45.502, 'street')]}

def new_page(ctx_or_browser, scheme='light', width=390, net=None, ctx=None):
    if ctx is None:
        ctx = ctx_or_browser.new_context(viewport={'width': width, 'height': 844}, color_scheme=scheme, timezone_id='America/Toronto', locale='fr-CA', accept_downloads=True)
        ctx.add_init_script("try{localStorage.setItem('gm.ui','full')}catch(e){}")
    pg = ctx.new_page(); errs = []; net = net if net is not None else []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    def route(r):
        u = r.request.url
        if u == 'https://local.test/':
            r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE)
        elif 'cdnjs.cloudflare.com/ajax/libs/jspdf' in u:
            r.fulfill(status=200, content_type='application/javascript', body=open(JSPDF, encoding='utf8').read())
        elif u.startswith('https://api.tomtom.com/search/2/search/'):
            net.append(('tomtom', u)); qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query); time.sleep(0.08)
            if qs.get('key') == ['BADKEY']: r.fulfill(status=403, body='{"error":"forbidden"}', content_type='application/json', headers={'access-control-allow-origin': '*'})
            else: r.fulfill(status=200, body=json.dumps(TT_OK), content_type='application/json', headers={'access-control-allow-origin': '*'})
        elif u.startswith('https://photon.komoot.io/api/'):
            net.append(('photon', u)); qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query); time.sleep(0.12)
            if getattr(new_page, 'photon_down', False): return r.abort()
            q = qs.get('q', [''])[0]
            body = PH_STREET if qs.get('layer') == ['street'] else PH_NOPC if 'sans' in q.lower() else PH_HOUSE
            r.fulfill(status=200, body=json.dumps(body), content_type='application/json', headers={'access-control-allow-origin': '*'})
        else:
            r.abort()
    pg.route('**/*', route)
    pg.goto('https://local.test/#agenda'); pg.wait_for_timeout(300)
    return ctx, pg, errs, net

def store(pg): return pg.evaluate("JSON.parse(localStorage.getItem('gm.web.db') || '{}')")
def clients(pg): return {k: v for k, v in store(pg).items() if k.startswith('clients/')}
def type_addr(pg, t, wait=600):
    pg.fill('#c-addr', ''); pg.click('#c-addr'); pg.keyboard.type(t); pg.wait_for_timeout(wait)
def new_client(pg):
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(200)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs, net = new_page(br)
    check('H1. Hosted page opens alone (no claude.ai): title, "Version rapide" strip, OpenStreetMap by default', pg.title() == 'Carnet du garage mobile' and pg.is_visible('#demo-bar') and 'OpenStreetMap' in pg.inner_text('#db-prov') and pg.locator('.tab:not([hidden])').count() == 6 and not errs, errs[:3])
    check('H1b. Owner tools available (hours button, + Réservation)', pg.locator('#top [data-act="new"]').count() == 1 and pg.locator('[data-act="hours-edit"]').count() == 1)
    new_client(pg)
    check('H2. Address field in fast mode invites to type', 'OpenStreetMap complète' in pg.inner_text('#c-addrmsg'))
    type_addr(pg, '1200 essai')
    ph_calls = [u for k, u in net if k == 'photon']
    qs = urllib.parse.parse_qs(urllib.parse.urlparse(ph_calls[-1]).query) if ph_calls else {}
    opts = pg.locator('#c-addrsug .opt')
    check('H3. One direct OpenStreetMap call (q, house layer, French, biased near Montréal)', len(ph_calls) == 1 and qs.get('q') == ['1200 essai'] and qs.get('layer') == ['house'] and qs.get('lang') == ['fr'] and qs.get('lat') and qs.get('lon'), ph_calls)
    check('H4. Canadian results only, Québec address first with postal code, credited to OpenStreetMap', opts.count() == 2 and opts.nth(0).locator('b').inner_text() == '1200 Rue Essai-Sud, Montréal QC H4P 2B5' and 'ON' in opts.nth(1).inner_text() and 'OpenStreetMap' in pg.inner_text('#c-addrsug .src'), [opts.nth(i).inner_text() for i in range(opts.count())])
    ms = pg.inner_text('#db-ms')
    check('H5. Strip shows how long the search took', 'dernière recherche :' in ms and ' ms' in ms, ms)
    pg.screenshot(path=os.path.join(SC, 'shot_web_osm.png'))
    opts.nth(0).click(); pg.wait_for_timeout(100)
    pg.fill('#c-first', 'Rapide'); pg.fill('#c-last', 'Test'); pg.fill('#c-phone', '5145550909'); pg.click('#c-save'); pg.wait_for_timeout(300)
    cl = list(clients(pg).values())
    check('H6. Fiche saved in this browser with address, postal code, position', len(cl) == 1 and cl[0]['address'] == '1200 Rue Essai-Sud, Montréal QC H4P 2B5' and cl[0]['postal'] == 'H4P 2B5' and cl[0]['geo'] == {'lat': 45.501, 'lon': -73.651} and 'Rapide Test' in pg.inner_text('#top'), cl)
    pg2 = ctx.new_page(); errs2 = []
    pg2.on('pageerror', lambda e: errs2.append(str(e)))
    pg2.route('**/*', lambda r: r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE) if r.request.url == 'https://local.test/' else r.abort())
    pg2.goto('https://local.test/'); pg2.wait_for_timeout(300); pg2.click('.tab[data-t="clients"]'); pg2.wait_for_timeout(150)
    check('H7. Second tab sees the fiche (saved, survives reopening)', 'Rapide Test' in pg2.inner_text('main'))
    pg.click('#top [data-act="back"]') if pg.locator('#top [data-act="back"]').count() else None
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(200)
    pg.fill('#c-first', 'Deux'); pg.fill('#c-last', 'Onglets'); pg.fill('#c-phone', '5145550808'); pg.fill('#c-addr', '9 rue Test, Montréal H4P 2B5'); pg.click('#c-save'); pg.wait_for_timeout(300)
    pg2.wait_for_timeout(300)
    check('H8. Live between tabs: the other tab updates by itself', 'Deux Onglets' in pg2.inner_text('main') and not errs2, errs2[:2])
    pg2.close()
    # street search, no postal code from OSM
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(200)
    type_addr(pg, 'rue essai')
    last = [u for k, u in net if k == 'photon'][-1]
    check('H9. Street without number: OpenStreetMap street layer, one line per street', urllib.parse.parse_qs(urllib.parse.urlparse(last).query).get('layer') == ['street'] and pg.locator('#c-addrsug .opt:not(.local)').count() == 1 and pg.locator('#c-addrsug .opt:not(.local) b').first.inner_text() == 'Rue Essai-Sud, Montréal QC')
    type_addr(pg, '55 sans code')
    pg.locator('#c-addrsug .opt').first.click(); pg.wait_for_timeout(100)
    pg.click('#c-email'); pg.wait_for_timeout(700)
    check('H10. OSM address without postal code: asks to add it, no false "code postal trouvé"', pg.input_value('#c-addr') == '55 Rue Sans-Code, Montréal QC' and 'Ajoute le code postal' in pg.inner_text('#c-addrmsg') and pg.inner_text('#c-addrfix').strip() == '', (pg.input_value('#c-addr'), pg.inner_text('#c-addrmsg'), pg.inner_text('#c-addrfix')))
    # TomTom key
    pg.click('#db-open'); pg.wait_for_timeout(50)
    check('H11. "Réglages de l\'essai" explains data stays on this device', 'restent dans ce navigateur' in pg.inner_text('#db-panel'))
    pg.click('#db-save'); pg.wait_for_timeout(50)
    check('H11b. Empty key refused politely', 'Colle d' in pg.inner_text('#db-note'))
    pg.fill('#db-key', 'TESTKEY123'); pg.click('#db-save'); pg.wait_for_timeout(50)
    check('H12. Key saved in this browser only, strip says TomTom en direct', pg.evaluate("localStorage.getItem('gm.web.ttkey')") == 'TESTKEY123' and 'TomTom en direct' in pg.inner_text('#db-prov') and 'TESTKEY123' not in PAGE)
    type_addr(pg, '1200 essai')
    tt = [u for k, u in net if k == 'tomtom']
    tq = urllib.parse.parse_qs(urllib.parse.urlparse(tt[-1]).query) if tt else {}
    check('H13. Direct TomTom call with the key and the same smart parameters', len(tt) == 1 and '/search/2/search/1200%20essai.json' in tt[0] and tq.get('key') == ['TESTKEY123'] and tq.get('typeahead') == ['true'] and tq.get('countrySet') == ['CA'] and tq.get('idxSet') == ['PAD,Addr'] and tq.get('language') == ['fr-CA'] and tq.get('lat') and tq.get('lon'), tt)
    check('H13b. TomTom answer shown, credited to TomTom', pg.locator('#c-addrsug .opt b').first.inner_text() == '1200 Rue Essai-Sud, Montréal QC H4P 2B5' and 'TomTom' in pg.inner_text('#c-addrsug .src'))
    pg.locator('#c-addrsug .opt').first.click(); pg.wait_for_timeout(100)
    check('H13c. Same address as a fiche: shown once ("Fiche de …"), picked with its position', 'Adresse déjà connue' in pg.inner_text('#c-addrmsg') and pg.locator('#c-sameaddr').inner_text().count('Rapide Test') >= 1, pg.inner_text('#c-addrmsg'))
    pg.fill('#db-key', 'BADKEY'); pg.click('#db-save'); pg.wait_for_timeout(50)
    n_ph = len([1 for k, u in net if k == 'photon'])
    type_addr(pg, '1200 essai-sud', 800)
    check('H14. Refused key: falls back to OpenStreetMap and says so', len([1 for k, u in net if k == 'photon']) == n_ph + 1 and 'Clé TomTom refusée' in pg.inner_text('#db-note') and pg.locator('#c-addrsug .opt').count() >= 1, pg.inner_text('#db-note'))
    pg.click('#db-unkey'); pg.wait_for_timeout(50)
    check('H15. "Retirer" removes the key', pg.evaluate("localStorage.getItem('gm.web.ttkey')") is None and 'OpenStreetMap' in pg.inner_text('#db-prov'))
    # network down
    new_page.photon_down = True
    type_addr(pg, '1300 essai', 700)
    check('H16. Search service down: soft message, typing still works', 'ne répond pas' in pg.inner_text('#c-ttnote') and pg.input_value('#c-addr') == '1300 essai', pg.inner_text('#c-ttnote'))
    new_page.photon_down = False
    pg.click('#top [data-act="cform-back"]'); pg.wait_for_timeout(150)
    # booking + invoice + PDF
    pg.click('.tab[data-t="agenda"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="new"]'); pg.wait_for_timeout(250)
    pg.fill('#cs-q', 'rapide'); pg.wait_for_timeout(120); pg.locator('#cs-results .crow').first.click(); pg.wait_for_timeout(250)
    pg.fill('#f-time', '10:00'); pg.click('#f-save'); pg.wait_for_timeout(300)
    jobs = [v for k, v in store(pg).items() if k.startswith('jobs/')]
    check('H17. Booking saved on the fiche', len(jobs) == 1 and jobs[0]['client']['name'] == 'Rapide Test' and jobs[0]['clientId'])
    pg.click('.tab[data-t="factures"]'); pg.wait_for_timeout(150); pg.click('[data-act="quick"]'); pg.wait_for_timeout(250)
    pg.fill('#cs-q', 'rapide'); pg.wait_for_timeout(120); pg.locator('#cs-results .crow').first.click(); pg.wait_for_timeout(250)
    pg.click('#f-save'); pg.wait_for_timeout(350)
    pg.locator('[data-act="addline"][data-v="mo"]').click(); pg.wait_for_timeout(50)
    pg.fill('#l0-desc', 'Diagnostic') if pg.input_value('#l0-desc') == '' else None
    pg.fill('#l0-price', '95'); pg.click('[data-act="finalize"]'); pg.wait_for_timeout(500)
    inv = [v['invoice'] for k, v in store(pg).items() if k.startswith('jobs/') and v.get('invoice', {}).get('number')]
    check('H18. Invoice numbered and saved', len(inv) == 1 and inv[0]['number'].startswith('F-'), inv)
    with pg.expect_download(timeout=15000) as dl:
        pg.click('[data-act="pdf"]')
    d = dl.value
    check('H19. PDF downloads as a normal file', d.suggested_filename.endswith('.pdf') and 'Rapide Test' in d.suggested_filename, d.suggested_filename)
    # reset
    pg.click('#db-open') if pg.is_hidden('#db-panel') else None
    pg.click('#db-reset'); pg.wait_for_timeout(50)
    check('H20. Erase asks for a second tap', 'encore' in pg.inner_text('#db-reset') and len(clients(pg)) == 2)
    pg.click('#db-reset'); pg.wait_for_timeout(300)
    check('H20b. Second tap erases the test data', store(pg) == {} and 'effacées' in pg.inner_text('#db-note'))
    check('H21. No script errors (the refused-key 403 is expected); no side-scroll', not [e for e in errs if 'status of 403' not in e] and pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), errs[:3])
    ctx.close()
    for scheme, w in (('dark', 390), ('light', 1100)):
        ctx, pg, errs, net = new_page(br, scheme=scheme, width=w)
        pg.click('#db-open'); pg.wait_for_timeout(50)
        pg.screenshot(path=os.path.join(SC, f'shot_web_{scheme}_{w}.png'))
        check(f'H22. {scheme} {w}px: strip and app render, no errors, no side-scroll', not errs and pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), errs[:3])
        ctx.close()
    br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
