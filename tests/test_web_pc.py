import json, os, time, math, urllib.parse
from playwright.sync_api import sync_playwright
exec(open("test_pclist.py").read().split("\nwith sync_playwright() as p:")[0])
PAGE = open('/home/claude/garage/web/index.html', encoding='utf8').read()
def nearest(lon, lat, rad):
    kx = 111320 * math.cos(math.radians(lat)); best = None; bd = 1e9
    for h in houses:
        d = math.hypot((h['lon'] - lon) * kx, (h['lat'] - lat) * 111320)
        if d < bd: bd, best = d, h
    return best if bd <= rad else None
def web_page(br, net):
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, locale='fr-CA', timezone_id='America/Toronto')
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    live = {'n': 0, 'max': 0}
    def route(r):
        u = r.request.url; pu = urllib.parse.urlparse(u); qs = urllib.parse.parse_qs(pu.query)
        hdr = {'access-control-allow-origin': '*'}
        if u == 'https://local.test/': return r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE)
        if u.startswith('https://api.tomtom.com/search/2/geocode/'):
            net.append(('tt-geo', u)); q = urllib.parse.unquote(pu.path.split('/geocode/')[1][:-5])
            res = [{'type': 'Street', 'address': {'streetName': 'Rue Saint-Essai', 'municipality': 'Montréal', 'postalCode': 'H2J', 'freeformAddress': 'Rue Saint-Essai, Montréal QC H2J'}, 'position': {'lat': CENTER[1], 'lon': CENTER[0]}}] if q == 'H2J 2L3' else []
            return r.fulfill(status=200, body=json.dumps({'summary': {}, 'results': res}), content_type='application/json', headers=hdr)
        if u.startswith('https://api.tomtom.com/search/2/reverseGeocode/'):
            net.append(('tt-rev', u)); live['n'] += 1; live['max'] = max(live['max'], live['n']); time.sleep(0.03); live['n'] -= 1
            lat, lon = map(float, urllib.parse.unquote(pu.path.split('/reverseGeocode/')[1][:-5]).split(','))
            h = nearest(lon, lat, float(qs.get('radius', ['100'])[0]))
            adr = [{'address': {'streetNumber': h['num'], 'streetName': h['street'], 'municipality': 'Montréal', 'postalCode': h['pc'][:3], 'extendedPostalCode': h['pc'], 'freeformAddress': f"{h['num']} {h['street']}, Montréal QC {h['pc']}"}, 'position': f"{h['lat']},{h['lon']}", 'matchType': 'AddressPoint'}] if h else []
            return r.fulfill(status=200, body=json.dumps({'summary': {}, 'addresses': adr}), content_type='application/json', headers=hdr)
        if u.startswith('https://photon.komoot.io/api/'):
            net.append(('ph-api', u)); q = qs.get('q', [''])[0]
            feats = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [want[0]['lon'], want[0]['lat']]}, 'properties': {'housenumber': want[0]['num'], 'street': 'Rue Saint-Essai', 'city': 'Montréal', 'postcode': 'H2J 2L3', 'state': 'Québec', 'countrycode': 'CA', 'type': 'house'}}] if q.upper().replace(' ', '') == 'H2J2L3' else []
            return r.fulfill(status=200, body=json.dumps({'type': 'FeatureCollection', 'features': feats}), content_type='application/json', headers=hdr)
        if u.startswith('https://photon.komoot.io/reverse'):
            net.append(('ph-rev', u)); h = nearest(float(qs['lon'][0]), float(qs['lat'][0]), float(qs.get('radius', ['0.1'])[0]) * 1000)
            feats = [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [h['lon'], h['lat']]}, 'properties': {'housenumber': h['num'], 'street': h['street'], 'city': 'Montréal', 'postcode': h['pc'], 'state': 'Québec', 'countrycode': 'CA', 'type': 'house'}}] if h else []
            return r.fulfill(status=200, body=json.dumps({'type': 'FeatureCollection', 'features': feats}), content_type='application/json', headers=hdr)
        return r.abort()
    pg.route('**/*', route); pg.goto('https://local.test/#agenda'); pg.wait_for_timeout(300)
    return ctx, pg, errs, live
def wait_done(pg):
    for _ in range(60):
        if 'Recherche des adresses' not in pg.inner_text('#c-addrsug'): return
        pg.wait_for_timeout(200)
with sync_playwright() as p:
    br = p.chromium.launch()
    for mode in ('TomTom', 'OpenStreetMap'):
        net = []; ctx, pg, errs, live = web_page(br, net)
        if mode == 'TomTom': pg.evaluate("localStorage.setItem('gm.web.ttkey', 'TESTKEY123')"); pg.reload(); pg.wait_for_timeout(300)
        pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(200)
        t0 = time.time(); pg.click('#c-addr'); pg.keyboard.type('H2J 2L3'); pg.wait_for_timeout(300); wait_done(pg); dt = time.time() - t0
        rows = pg.locator('#c-addrsug .opt:not(.local)')
        inpc = [rows.nth(i).locator('b').inner_text() for i in range(rows.count()) if 'Dans H2J 2L3' in rows.nth(i).inner_text()]
        expn = [h['num'] + ' Rue Saint-Essai' for h in want]
        kinds = sorted(set(k for k, u in net))
        check(f'V1. Fast version ({mode}): every address of H2J 2L3 listed in order', inpc == expn, (len(inpc), len(expn), inpc[:5]))
        check(f'V2. Fast version ({mode}): uses the right services, ≤ 4 at a time', (kinds == ['tt-geo', 'tt-rev'] if mode == 'TomTom' else kinds == ['ph-api', 'ph-rev']) and live['max'] <= 4, (kinds, live['max']))
        print(f'   ({mode}: {len([1 for k, u in net if k.endswith("rev")])} lookups, {dt:.1f} s with simulated 30 ms answers)')
        rows.first.click(); pg.wait_for_timeout(100)
        check(f'V3. Fast version ({mode}): picking fills the address with H2J 2L3', pg.input_value('#c-addr').endswith('H2J 2L3') and mode in pg.inner_text('#c-addrmsg'), (pg.input_value('#c-addr'), pg.inner_text('#c-addrmsg')))
        check(f'V4. Fast version ({mode}): no script errors', not errs, errs[:3])
        ctx.close()
    br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
