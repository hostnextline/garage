import json, os, time, urllib.parse
from playwright.sync_api import sync_playwright
SC = os.path.dirname(os.path.abspath(__file__))
PAGE = open('/home/claude/garage/web/index.html', encoding='utf8').read()
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)) if detail and not cond else ''))
FAKE_GOOGLE = r"""
(function(){
  var KEY = %(key)s, CB = %(cb)s;
  window.__gmScripts = (window.__gmScripts || 0) + 1; window.__gmCalls = window.__gmCalls || []; window.__gmTokens = 0;
  var ADDR = [
    {text:'1200 Rue Essai-Sud, Montréal, QC, Canada', types:['street_address','geocode'], formatted:'1200 Rue Essai-Sud, Montréal, QC H4P 2B5, Canada', lat:45.501, lng:-73.651},
    {text:'1200 Rue Essai, Ottawa, ON, Canada', types:['street_address','geocode'], formatted:'1200 Rue Essai, Ottawa, ON K1A 0B1, Canada', lat:45.42, lng:-75.7},
    {text:'Essaiville, QC, Canada', types:['locality','political','geocode'], formatted:'Essaiville, QC, Canada', lat:46, lng:-72}];
  var ROUTES = [
    {text:'Rue Essai-Sud, Montréal, QC, Canada', types:['route','geocode'], formatted:'Rue Essai-Sud, Montréal, QC H4P, Canada', lat:45.5, lng:-73.65},
    {text:'Essaiville, QC, Canada', types:['locality','political','geocode'], formatted:'Essaiville, QC, Canada', lat:46, lng:-72}];
  function LL(a, b){ return {lat:function(){ return a; }, lng:function(){ return b; }}; }
  function Token(){ window.__gmTokens++; this.id = 't' + window.__gmTokens; }
  var AS = {fetchAutocompleteSuggestions:function(req){
    window.__gmCalls.push({kind:'auto', input:req.input, regions:req.includedRegionCodes, types:req.includedPrimaryTypes, language:req.language, origin:req.origin, bias:!!req.locationBias, token:req.sessionToken && req.sessionToken.id});
    if (KEY === 'BADKEY'){ setTimeout(function(){ window.gm_authFailure && window.gm_authFailure(); }, 0); return Promise.reject(new Error('REQUEST_DENIED: The provided API key is invalid.')); }
    if (window.__gmStrict && req.locationBias) return Promise.reject(new Error('InvalidValueError: in property locationBias: not a valid value'));
    var q = String(req.input).toLowerCase(), num = (q.match(/^\d+/) || [''])[0];
    var list = num ? ADDR.filter(function(d){ return d.text.indexOf(num) === 0 && /essai/.test(q) || d.types[0] === 'locality'; }) : ROUTES;
    if (!/essai/.test(q)) list = [];
    return new Promise(function(r){ setTimeout(function(){ r({suggestions:list.map(function(d){ return {placePrediction:{text:{text:d.text, toString:function(){ return d.text; }}, types:d.types, toPlace:function(){
      var pl = {formattedAddress:undefined, location:undefined, fetchFields:function(o){ window.__gmCalls.push({kind:'details', text:d.text, fields:o.fields}); pl.formattedAddress = d.formatted; pl.location = LL(d.lat, d.lng); return Promise.resolve({place:pl}); }};
      return pl; }}}; })}); }, 40); });
  }};
  window.google = {maps:{importLibrary:function(n){ return Promise.resolve(n === 'places' ? {AutocompleteSessionToken:Token, AutocompleteSuggestion:AS} : {}); }}};
  setTimeout(function(){ window[CB] && window[CB](); }, 10);
})();
"""
PH = {'type': 'FeatureCollection', 'features': [{'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [-73.651, 45.501]}, 'properties': {'housenumber': '1200', 'street': 'Rue Essai-Sud', 'city': 'Montréal', 'postcode': 'H4P 2B5', 'state': 'Québec', 'countrycode': 'CA', 'type': 'house'}}]}
def new_page(br, scheme='light', gkey=None, ttkey=None, strict=False):
    ctx = br.new_context(viewport={'width': 390, 'height': 844}, color_scheme=scheme, locale='fr-CA', timezone_id='America/Toronto')
    pg = ctx.new_page(); errs = []; net = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' and 'fonts.g' not in m.text and 'ERR_FAILED' not in m.text else None)
    def route(r):
        u = r.request.url; qs = urllib.parse.parse_qs(urllib.parse.urlparse(u).query); hdr = {'access-control-allow-origin': '*'}
        if u == 'https://local.test/': return r.fulfill(status=200, content_type='text/html; charset=utf-8', body=PAGE)
        if u.startswith('https://maps.googleapis.com/maps/api/js'):
            net.append(('gjs', u))
            return r.fulfill(status=200, content_type='application/javascript', body=FAKE_GOOGLE % {'key': json.dumps(qs.get('key', [''])[0]), 'cb': json.dumps(qs.get('callback', [''])[0])})
        if u.startswith('https://photon.komoot.io/'):
            net.append(('photon', u)); return r.fulfill(status=200, body=json.dumps(PH), content_type='application/json', headers=hdr)
        if u.startswith('https://api.tomtom.com/'):
            net.append(('tomtom', u)); return r.fulfill(status=200, body=json.dumps({'results': []}), content_type='application/json', headers=hdr)
        return r.abort()
    pg.route('**/*', route)
    init = []
    if gkey: init.append(f"localStorage.setItem('gm.web.gkey', {json.dumps(gkey)});")
    if ttkey: init.append(f"localStorage.setItem('gm.web.ttkey', {json.dumps(ttkey)});")
    if strict: init.append("window.__gmStrict = true;")
    if init: pg.add_init_script("try{ if (!sessionStorage.getItem('__init')){ " + "".join(init) + " sessionStorage.setItem('__init','1'); } }catch(e){}")
    pg.goto('https://local.test/'); pg.wait_for_timeout(300)
    return ctx, pg, errs, net
def calls(pg): return pg.evaluate('window.__gmCalls || []')
def store(pg): return pg.evaluate("JSON.parse(localStorage.getItem('gm.web.db') || '{}')")
def clients(pg): return {k: v for k, v in store(pg).items() if k.startswith('clients/')}
def new_client(pg):
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(200)
def type_addr(pg, t, wait=500):
    pg.fill('#c-addr', ''); pg.click('#c-addr'); pg.keyboard.type(t); pg.wait_for_timeout(wait)
def opts(pg): return [x.inner_text() for x in pg.locator('#c-addrsug .opt:not(.local)').all()]
AT = '1200 Rue Essai-Sud, Montréal QC H4P 2B5'
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx, pg, errs, net = new_page(br)
    pg.click('#db-open'); pg.wait_for_timeout(50)
    check('G0. "Réglages de l\'essai" has a Google Maps key field', pg.locator('#db-gkey').count() == 1 and 'Google Maps' in pg.inner_text('#db-panel'))
    pg.click('#db-gsave'); pg.wait_for_timeout(50)
    check('G0b. Empty Google key refused politely', 'Colle d\'abord ta clé Google' in pg.inner_text('#db-note'))
    pg.fill('#db-gkey', 'GOODKEY'); pg.click('#db-gsave'); pg.wait_for_timeout(100)
    check('G1. Key saved in this browser, strip says "Google Maps en direct", nothing loaded yet', pg.evaluate("localStorage.getItem('gm.web.gkey')") == 'GOODKEY' and 'Google Maps en direct' in pg.inner_text('#db-prov') and not [1 for k, u in net if k == 'gjs'] and 'GOODKEY' not in PAGE)
    pg.click('#db-open'); pg.wait_for_timeout(50)
    new_client(pg)
    type_addr(pg, '1200 essai', 700)
    gjs = [u for k, u in net if k == 'gjs']; gq = urllib.parse.parse_qs(urllib.parse.urlparse(gjs[0]).query) if gjs else {}
    c = [x for x in calls(pg) if x['kind'] == 'auto']
    check('G2. Google loaded once with the key, in French for Canada', len(gjs) == 1 and gq.get('key') == ['GOODKEY'] and gq.get('language') == ['fr'] and gq.get('region') == ['CA'] and gq.get('loading') == ['async'], gjs)
    check('G3. Suggestions asked for Canada, in French, near the start point, with a session', c and c[-1]['input'] == '1200 essai' and c[-1]['regions'] == ['ca'] and c[-1]['language'] == 'fr-CA' and c[-1]['origin'] and c[-1]['bias'] and c[-1]['token'], c[-1:] )
    o = opts(pg)
    check('G4. Addresses shown cleaned up, city dropped, Ottawa flagged, "Google Maps" credited', len(o) == 2 and o[0].startswith('1200 Rue Essai-Sud, Montréal QC') and 'hors Québec' in o[1] and 'Essaiville' not in ' '.join(o) and 'Adresses proposées par Google Maps' in pg.inner_text('#c-addrsug'), o)
    pg.screenshot(path=os.path.join(SC, 'shot_google.png'))
    t1 = c[-1]['token']
    pg.locator('#c-addrsug .opt').first.click(); pg.wait_for_timeout(300)
    d = [x for x in calls(pg) if x['kind'] == 'details']
    check('G5. Picking fills the full address with its postal code (Google details)', pg.input_value('#c-addr') == AT and d and d[-1]['fields'] == ['formattedAddress', 'location'], (pg.input_value('#c-addr'), d[-1:]))
    check('G5b. Hint: "Adresse trouvée sur Google Maps · Code postal H4P 2B5 · zone H4P"', 'Adresse trouvée sur Google Maps · Code postal H4P 2B5 · zone H4P' in pg.inner_text('#c-addrmsg'), pg.inner_text('#c-addrmsg'))
    pg.fill('#c-first', 'Gina'); pg.fill('#c-last', 'Google'); pg.fill('#c-phone', '5145550123'); pg.click('#c-save'); pg.wait_for_timeout(400)
    cl = [v for v in clients(pg).values() if v['lastName'] == 'Google']
    check('G6. Fiche saved with address and postal code; Google position not kept (Google rule)', len(cl) == 1 and cl[0]['address'] == AT and cl[0]['postal'] == 'H4P 2B5' and cl[0].get('geo') is None, cl)
    check('G6b. Google address not kept in "déjà utilisées" on this device', AT not in (pg.evaluate("localStorage.getItem('gm.addr.recent')") or ''))
    pg.click('.tab[data-t="clients"]'); pg.wait_for_timeout(100); pg.click('#top [data-act="cl-new"]'); pg.wait_for_timeout(200)
    type_addr(pg, '180-1200 essai', 700)
    c = [x for x in calls(pg) if x['kind'] == 'auto']
    check('G6c. The address already on Gina\'s fiche shows first, marked "Fiche de Gina Google"', 'Fiche de Gina Google' in pg.locator('#c-addrsug .opt').first.inner_text())
    check('G7. New search = new Google session; "180-" kept out of the query', c[-1]['input'] == '1200 essai' and c[-1]['token'] != t1, (c[-1], t1))
    pg.locator('#c-addrsug .opt:not(.local)').first.click(); pg.wait_for_timeout(300)
    check('G7b. Picked with the unit in front, once', pg.input_value('#c-addr') == '180-' + AT, pg.input_value('#c-addr'))
    type_addr(pg, 'rue essai', 700)
    c = [x for x in calls(pg) if x['kind'] == 'auto']
    check('G8. Street without number: asks Google for streets only, shows the street', c[-1]['types'] == ['route'] and opts(pg) and opts(pg)[0].startswith('Rue Essai-Sud, Montréal QC') and 'ajoute ensuite le numéro' in opts(pg)[0], (c[-1], opts(pg)))
    type_addr(pg, 'H2J 2L3', 500)
    n_auto = len([x for x in calls(pg) if x['kind'] == 'auto'])
    check('G9. Postal code alone: no postal list with Google, asks for the civic number', not [1 for k, u in net if k == 'tomtom'] and 'ajoute le numéro civique devant' in pg.inner_text('#c-addrmsg') and 'Continue le code postal' not in (pg.inner_text('#c-addrsug') if pg.is_visible('#c-addrsug') else ''), pg.inner_text('#c-addrmsg'))
    type_addr(pg, '1200 rue essai-sud montreal', 600); pg.keyboard.press('Escape'); pg.click('#c-email'); pg.wait_for_timeout(700)
    check('G10. Address typed by hand: Google finds the postal code ("Utiliser cette adresse")', 'Code postal trouvé par Google Maps' in pg.inner_text('#c-addrfix') and AT in pg.inner_text('#c-addrfix'), pg.inner_text('#c-addrfix'))
    pg.click('#c-addrfix [data-act="addr-fix"]'); pg.wait_for_timeout(100)
    check('G10b. Fixed: full address, postal code', pg.input_value('#c-addr') == AT and 'Code postal H4P 2B5' in pg.inner_text('#c-addrmsg'))
    check('G11. No script errors', not errs, errs[:3])
    ctx.close()
    # Google refuses an option: retried without it
    ctx, pg, errs, net = new_page(br, gkey='GOODKEY', strict=True)
    new_client(pg); type_addr(pg, '1200 essai', 800)
    c = [x for x in calls(pg) if x['kind'] == 'auto']
    check('G12. If Google refuses an option, it asks again without it and still shows addresses', len(c) == 2 and c[0]['bias'] and not c[1]['bias'] and len(opts(pg)) == 2, (c, opts(pg)))
    check('G12b. No script errors', not errs, errs[:3])
    ctx.close()
    # bad key: clear message, falls back
    ctx, pg, errs, net = new_page(br, gkey='BADKEY')
    new_client(pg); type_addr(pg, '1200 essai', 900)
    check('G13. Key refused: says what to check in Google Cloud, falls back to OpenStreetMap, addresses still shown', 'Google refuse la clé' in pg.inner_text('#db-note') and 'OpenStreetMap' in pg.inner_text('#db-prov') and [1 for k, u in net if k == 'photon'] and len(opts(pg)) >= 1, (pg.inner_text('#db-note'), opts(pg)))
    check('G13b. No script errors', not [e for e in errs if 'REQUEST_DENIED' not in e], errs[:3])
    ctx.close()
    # removing the key after Google was loaded reloads the page and goes back to TomTom
    ctx, pg, errs, net = new_page(br, gkey='GOODKEY', ttkey='TTKEY')
    new_client(pg); type_addr(pg, '1200 essai', 700)
    pg.click('#db-open'); pg.wait_for_timeout(50); pg.click('#db-gunkey'); pg.wait_for_timeout(1500)
    check('G14. "Retirer" the Google key: page reloads and goes back to TomTom', pg.evaluate("localStorage.getItem('gm.web.gkey')") is None and 'TomTom en direct' in pg.inner_text('#db-prov'))
    ctx.close()
    ctx, pg, errs, net = new_page(br, scheme='dark', gkey='GOODKEY')
    new_client(pg); type_addr(pg, '1200 essai', 700)
    pg.screenshot(path=os.path.join(SC, 'shot_google_dark.png'))
    check('G15. Dark mode: list renders, no errors, no side-scroll', len(opts(pg)) == 2 and not errs and pg.evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1'), errs[:3])
    ctx.close(); br.close()
print('\n%d/%d passed' % (sum(1 for r in results if r[1]), len(results)))
