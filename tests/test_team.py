"""End-to-end test of the team version against the local Supabase copy:
real Postgres + rules, real Auth, real edge functions; GoHighLevel and the road router are local fakes."""
import json, os, re, subprocess, time, hashlib, urllib.request, datetime
from playwright.sync_api import sync_playwright

SC = os.path.dirname(os.path.abspath(__file__))
K = json.load(open(os.path.join(SC, 'stack/keys.json')))
BASE = 'http://127.0.0.1:8088/'
API = 'http://127.0.0.1:54321'
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def psql(sql):
    return subprocess.run(['psql', '-h', '127.0.0.1', '-p', '54322', '-U', 'postgres', '-Atq', '-c', sql], capture_output=True, text=True).stdout.strip()
def http(method, url, body=None, token=None, headers=None):
    h = {'Content-Type': 'application/json', 'apikey': K['anon'], 'Authorization': 'Bearer ' + (token or K['anon'])}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            t = r.read().decode(); return json.loads(t) if t else None
    except urllib.error.HTTPError as e:
        return {'_status': e.code, '_body': e.read().decode()}
def token(email, pw): return http('POST', API + '/auth/v1/token?grant_type=password', {'email': email, 'password': pw})['access_token']
def doc_set(tok, path, data): return http('POST', API + '/rest/v1/rpc/doc_set', {'p_path': path, 'p_data': data}, tok)
def ghl_log(): return json.loads(urllib.request.urlopen('http://127.0.0.1:9200/__log').read())
def ghl_reset(): urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9200/__reset', data=b'{}', method='POST'))
TODAY = datetime.date.today().isoformat()

psql("truncate public.members, public.docs, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks, public.setup_codes, public.app_secrets cascade; delete from auth.users;")
ghl_reset()
CODE = 'R4ND-0M7X-Q2PZ'
psql("insert into public.setup_codes (code_hash) values ('%s')" % hashlib.sha256(CODE.replace('-', '').encode()).hexdigest())

def ctx_for(browser, geo=None, perms=True):
    c = browser.new_context(viewport={'width': 390, 'height': 844}, timezone_id='America/Toronto', locale='fr-CA',
                            geolocation=geo, permissions=(['geolocation', 'clipboard-read', 'clipboard-write'] if perms else []))
    c.route('https://tile.openstreetmap.org/**', lambda r: r.fulfill(status=200, content_type='image/png', body=b''))
    c.route('https://fonts.googleapis.com/**', lambda r: r.fulfill(status=200, content_type='text/css', body=''))
    c.route('https://photon.komoot.io/**', lambda r: r.fulfill(status=200, content_type='application/json', body='{"type":"FeatureCollection","features":[]}'))
    return c
ERRS = []
def page_for(c, name):
    p = c.new_page()
    p.on('pageerror', lambda e: ERRS.append(name + ': ' + str(e)))
    p.on('console', lambda m: ERRS.append(name + ': ' + m.text) if m.type == 'error' and not re.search(r'realtime|websocket|WebSocket|ERR_|404|Failed to load resource', m.text) else None)
    return p
def no_hscroll(p): return p.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')
def visible_tabs(p): return p.evaluate("[...document.querySelectorAll('.tab')].filter(b => !b.hidden && b.offsetParent).map(b => b.textContent.trim())")
def toast_has(p, text, ms=8000):
    try:
        p.wait_for_function('t => { const e = document.getElementById("toast"); return e && !e.hidden && e.textContent.includes(t); }', arg=text, timeout=ms); return True
    except Exception: return False
def login(p, email, pw):
    p.goto(BASE); p.wait_for_selector('#gate #g-email', timeout=10000)
    p.fill('#g-email', email); p.fill('#g-pw', pw); p.click('#g-go')
def resync(p): p.evaluate('window.__supa.resync(true)'); p.wait_for_timeout(600)

with sync_playwright() as pw:
    br = pw.chromium.launch()

    # ---------- 1. first owner ----------
    oc = ctx_for(br); op = page_for(oc, 'owner')
    op.goto(BASE); op.wait_for_selector('#gate #g-code', timeout=10000)
    check('fresh garage shows « Première mise en route »', 'Première mise en route' in op.text_content('#g-title'))
    op.fill('#g-code', 'r4nd 0m7x q2pz'); op.fill('#g-name', 'Hassan Banho'); op.fill('#g-mech', 'Hassan'); op.fill('#g-email', 'hassan@garage.test'); op.fill('#g-pw', 'court')
    op.click('#g-go'); op.wait_for_timeout(1200)
    check('short password refused on setup', '8 caractères' in (op.text_content('#g-msg') or ''))
    op.fill('#g-pw', 'Motdepasse-2026'); op.click('#g-go')
    op.wait_for_selector('#gate', state='detached', timeout=15000)
    op.wait_for_selector('.acct', timeout=10000)
    check('owner signed in after setup', 'Hassan Banho' in op.text_content('.acct') and 'Propriétaire' in op.text_content('.acct'))
    check('owner tabs: Agenda Clients Factures Carte Réglages', visible_tabs(op) == ['Agenda', 'Clients', 'Factures', 'Carte', 'Réglages'], visible_tabs(op))
    check('owner (with a mechanic name) gets the workday card', op.locator('text=Début de journée').count() == 1)
    check('owner agenda no sideways scroll', no_hscroll(op))
    otok = token('hassan@garage.test', 'Motdepasse-2026')
    check('setup code used up', psql('select count(*) from public.setup_codes') == '0')
    r = doc_set(otok, 'config/main', {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Hassan', 'Saleh', 'Ali'], 'rate': 120, 'taxesOn': True, 'startNo': 1, 'prefix': 'F-'})
    check('config saved', r is None or '_status' not in (r or {}), r)
    op.reload(); op.wait_for_selector('.acct', timeout=10000)
    check('session kept after reload (no login screen)', op.locator('#gate').count() == 0)

    # ---------- 2. team & access ----------
    op.goto(BASE + '#reglages'); op.wait_for_selector('text=Gérer l\'équipe et les accès', timeout=8000)
    op.click('text=Gérer l\'équipe et les accès'); op.wait_for_selector('#nw-name', timeout=8000)
    op.wait_for_selector('.eqp', timeout=8000)
    check('team list shows the owner', 'hassan@garage.test' in op.text_content('main') and '(toi)' in op.text_content('main'))
    op.fill('#nw-name', 'Saleh Haddad'); op.fill('#nw-email', 'saleh@garage.test'); op.select_option('#nw-role', 'mecano')
    op.click('[data-act="eq-add"]'); op.wait_for_timeout(300)
    check('mecano without agenda name refused', 'Choisis son nom' in (op.text_content('#nw-err') or ''))
    op.select_option('#nw-mech', 'Saleh'); op.click('[data-act="eq-add"]')
    op.wait_for_selector('.created', timeout=10000)
    cred = op.text_content('.cred'); m = re.search(r'Mot de passe temporaire : (Garage-[A-Z0-9]{4}-[A-Z0-9]{4})', cred)
    check('account created with temporary password to send', m is not None and 'saleh@garage.test' in cred and BASE in cred, cred)
    SALEH_PW = m.group(1) if m else ''
    check('credentials card has copy / text / email', op.locator('.created [data-act="eq-copycred"]').count() == 1 and op.locator('.created a[href^="sms:"]').count() == 1 and op.locator('.created a[href^="mailto:saleh@garage.test"]').count() == 1)
    check('team screen no sideways scroll', no_hscroll(op))
    op.screenshot(path=os.path.join(SC, 'team_equipe.png'), full_page=True)
    op.click('[data-act="eq-hidecred"]')
    op.fill('#nw-name', 'Lina Bureau'); op.fill('#nw-email', 'lina@garage.test'); op.select_option('#nw-role', 'bureau'); op.click('[data-act="eq-add"]')
    op.wait_for_selector('.created', timeout=10000); LINA_PW = re.search(r'(Garage-[A-Z0-9]{4}-[A-Z0-9]{4})', op.text_content('.cred')).group(1); op.click('[data-act="eq-hidecred"]')
    op.fill('#nw-name', 'Ali'); op.fill('#nw-email', 'ali@garage.test'); op.select_option('#nw-role', 'mecano'); op.select_option('#nw-mech', 'Ali'); op.click('[data-act="eq-add"]')
    op.wait_for_selector('.created', timeout=10000); ALI_PW = re.search(r'(Garage-[A-Z0-9]{4}-[A-Z0-9]{4})', op.text_content('.cred')).group(1); op.click('[data-act="eq-hidecred"]')
    op.fill('#nw-name', 'Double'); op.fill('#nw-email', 'saleh@garage.test'); op.select_option('#nw-role', 'bureau'); op.click('[data-act="eq-add"]'); op.wait_for_timeout(1500)
    check('same email refused with clear message', 'déjà un compte' in (op.text_content('#nw-err') or ''), op.text_content('#nw-err'))
    check('4 people listed', op.locator('.eqp').count() == 4, op.locator('.eqp').count())
    # GoHighLevel
    check('texts not plugged at first', 'Pas branché' in op.text_content('main'))
    op.fill('#gh-token', 'pit-good-token'); op.fill('#gh-loc', 'loc123'); op.click('[data-act="gh-save"]')
    check('GHL saved', toast_has(op, 'GoHighLevel branché'))
    op.wait_for_timeout(300)
    check('GHL badge shows plugged, key masked', 'Branché' in op.text_content('main') and '…oken' in op.text_content('main') and 'pit-good-token' not in op.content())
    op.fill('#gh-test', '514 555 0000'); op.click('[data-act="gh-test"]')
    check('test text sent', toast_has(op, 'Texto test envoyé', 10000))
    lg = ghl_log()
    check('test text reached GoHighLevel', any(x['path'] == '/conversations/messages' and 'Test du garage mobile' in x['body'].get('message', '') for x in lg), lg[-2:])

    # seed the day: Marie (Saleh), Paul (Ali)
    doc_set(otok, 'clients/c1', {'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '514 555-0101', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3', 'geo': {'lat': 45.5265, 'lon': -73.5841}})
    doc_set(otok, 'clients/c2', {'firstName': 'Paul', 'lastName': 'Roy', 'phone': '438 555-0202', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1', 'geo': {'lat': 45.5130, 'lon': -73.5600}})
    snap = lambda c, cid: {'id': cid, 'firstName': c['firstName'], 'lastName': c['lastName'], 'name': c['firstName'] + ' ' + c['lastName'], 'phone': c['phone'], 'address': c['address'], 'postal': c['postal'], 'geo': c['geo']}
    c1 = {'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '514 555-0101', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3', 'geo': {'lat': 45.5265, 'lon': -73.5841}}
    c2 = {'firstName': 'Paul', 'lastName': 'Roy', 'phone': '438 555-0202', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1', 'geo': {'lat': 45.5130, 'lon': -73.5600}}
    doc_set(otok, 'jobs/j1', {'date': TODAY, 'time': '14:00', 'durationMin': 60, 'mechanic': 'Saleh', 'clientId': 'c1', 'client': snap(c1, 'c1'), 'vehicle': {'make': 'Honda', 'model': 'Civic', 'year': '2018'}, 'services': ["Changement d'huile et filtre"], 'service': "Changement d'huile et filtre", 'status': 'planifie', 'createdAt': 1})
    doc_set(otok, 'jobs/j2', {'date': TODAY, 'time': '10:00', 'durationMin': 60, 'mechanic': 'Ali', 'clientId': 'c2', 'client': snap(c2, 'c2'), 'vehicle': {'make': 'Ford'}, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'planifie', 'createdAt': 2})

    # ---------- 3. mechanic: his day ----------
    sc = ctx_for(br, geo={'latitude': 45.5010, 'longitude': -73.6000, 'accuracy': 8}); sp = page_for(sc, 'saleh')
    login(sp, 'saleh@garage.test', 'mauvais-mdp'); sp.wait_for_timeout(1500)
    check('wrong password message', 'incorrect' in (sp.text_content('#g-msg') or ''))
    sp.fill('#g-pw', SALEH_PW); sp.click('#g-go'); sp.wait_for_selector('.acct', timeout=15000)
    check('mechanic signed in', 'Saleh Haddad' in sp.text_content('.acct') and 'Mécano' in sp.text_content('.acct'))
    check('mechanic tabs: Agenda Clients Factures', visible_tabs(sp) == ['Agenda', 'Clients', 'Factures'], visible_tabs(sp))
    sp.wait_for_timeout(800)
    main = sp.text_content('main')
    check('mechanic sees his job (Marie)', 'Marie' in main, main[:300])
    check('mechanic does not see Ali\'s job (Paul)', 'Paul' not in main)
    check('no « + Réservation » for a mechanic', sp.locator('[data-act="new"]').count() == 0)
    check('no mechanic filter chips for a mechanic', sp.locator('[data-act="mech"]').count() == 0)
    check('first-time workday explanation (Loi 25)', 'gardées 30 jours' in main and 'Rien n\'est envoyé avant' in main)
    sp.goto(BASE + '#reglages'); sp.wait_for_timeout(500)
    check('mechanic cannot open Réglages (back to agenda)', sp.locator('.tab[data-t="agenda"][aria-current="page"]').count() == 1)
    sp.goto(BASE + '#carte'); sp.wait_for_timeout(500)
    check('mechanic cannot open the map', sp.locator('#map-slot').count() == 0)
    sp.goto(BASE + '#agenda'); sp.wait_for_selector('[data-act="sh-start"]')
    check('mechanic agenda no sideways scroll', no_hscroll(sp))
    sp.screenshot(path=os.path.join(SC, 'team_mech_start.png'))
    sp.click('[data-act="sh-start"]')
    sp.wait_for_selector('text=Journée en cours', timeout=8000)
    try:
        sp.wait_for_function('() => /Position envoyée/.test((document.getElementById("sh-line")||{}).textContent||"")', timeout=12000); ok = True
    except Exception: ok = False
    check('workday on: position sent line', ok, sp.text_content('#sh-line'))
    live = psql("select on_shift, round(lat::numeric,4), round(lon::numeric,4) from public.mech_live l join public.members m using (user_id) where m.mechanic='Saleh'")
    check('server has his live position', live == 't|45.5010|-73.6000', live)
    check('one point stored for the day path', psql("select count(*) from public.mech_positions") == '1')

    # ---------- 4. en route ----------
    sp.click('[data-act="open"][data-id="j1"]'); sp.wait_for_selector('.er', timeout=8000)
    btn = sp.locator('.er-go')
    check('big button « Je pars : aviser Marie »', btn.count() == 1 and 'Je pars : aviser Marie' in btn.text_content(), btn.text_content() if btn.count() else '')
    check('job page tells Marie gets a text', 'Marie reçoit un texto' in sp.text_content('.er'))
    check('job page no sideways scroll', no_hscroll(sp))
    btn.click()
    check('toast « Texto envoyé à Marie ✓ »', toast_has(sp, 'Texto envoyé à Marie', 15000))
    sp.wait_for_selector('.er-eta', timeout=8000)
    check('ETA shown on job page', re.search(r'\d{1,2} h \d{2}', sp.text_content('.er-eta')) is not None, sp.text_content('.er-eta'))
    link = sp.get_attribute('.er a.btn.steel', 'href')
    check('« Voir le suivi » link', link and link.startswith(BASE + 'suivi.html#t='), link)
    check('job status is « En route » on the server', psql("select data->>'status' from public.docs where path='jobs/j1'") == 'route')
    lg = ghl_log(); sms = [x for x in lg if x['path'] == '/conversations/messages']
    check('text to Marie through GoHighLevel', sms and 'Bonjour Marie, Saleh de Garage NextLine est en route vers chez vous' in sms[-1]['body']['message'] and link in sms[-1]['body']['message'], sms[-1:] )
    up = [x for x in lg if x['path'] == '/contacts/upsert'][-1]
    check('Marie created/updated in GoHighLevel contacts', up['body']['phone'] == '+15145550101' and up['body']['lastName'] == 'Tremblay')
    check('« Texto envoyé ✓ » line', 'Texto envoyé' in sp.text_content('.er'))
    sp.locator('.er').screenshot(path=os.path.join(SC, 'team_enroute.png'))
    check('text-it-myself link pre-filled', sp.locator('.er a[href^="sms:+15145550101?&body="]').count() == 1)

    # ---------- 5. the client's page ----------
    cc = ctx_for(br, perms=False); cp = page_for(cc, 'client')
    cp.goto(link); cp.wait_for_function('() => /est en route/.test(document.getElementById("title").textContent)', timeout=10000)
    check('client page: « Bonjour Marie, Saleh est en route »', cp.text_content('#title') == 'Bonjour Marie, Saleh est en route', cp.text_content('#title'))
    check('client page: garage name', cp.text_content('#garage') == 'Garage NextLine')
    check('client page: arrival time', not cp.locator('#eta').is_hidden() and re.search(r'\d{1,2} h \d{2}', cp.text_content('#eta-time')) is not None, cp.text_content('#eta'))
    check('client page: live position', 'Position en direct' in cp.text_content('#state'))
    check('client page: van + home on the map + route line', cp.locator('.pin').count() == 2 and cp.locator('path.leaflet-interactive').count() >= 1)
    check('client page: no last name, no phone', 'Tremblay' not in cp.content() and '555' not in cp.text_content('body'))
    check('client page no sideways scroll', no_hscroll(cp))
    cp.screenshot(path=os.path.join(SC, 'team_client.png'))
    before = cp.evaluate("document.querySelectorAll('.pin-wrap')[1] && document.querySelectorAll('.pin-wrap')[1].style.transform")
    eta_before = cp.text_content('#eta-left')
    sc.set_geolocation({'latitude': 45.5200, 'longitude': -73.5900, 'accuracy': 6})
    try:
        sp.wait_for_function('() => true', timeout=100)
        ok = False
        for _ in range(50):
            if psql("select round(lat::numeric,3) from public.mech_live l join public.members m using (user_id) where m.mechanic='Saleh'") == '45.520': ok = True; break
            time.sleep(0.5)
    except Exception: ok = False
    check('phone movement reaches the server', ok)
    time.sleep(11)
    after = cp.evaluate("document.querySelectorAll('.pin-wrap')[1] && document.querySelectorAll('.pin-wrap')[1].style.transform")
    check('client sees the van move (page updates by itself)', before != after, (before, after))
    check('client ETA recalculated', cp.text_content('#eta-left') != eta_before, (eta_before, cp.text_content('#eta-left'), http('POST', API + '/rest/v1/rpc/get_track', {'p_token': link.split('t=')[1]})))

    # ---------- 6. office map ----------
    op.goto(BASE + '#carte'); op.wait_for_selector('#gm-map', timeout=10000)
    try: op.wait_for_selector('.mc', timeout=10000); ok = True
    except Exception: ok = False
    check('map tab: mechanics list', ok and 'Saleh Haddad' in op.text_content('main'))
    check('map tab: Saleh « En route » with arrival', 'En route vers Marie' in op.text_content('main') and op.locator('.gm-map .gm-pin.p-route').count() == 1, op.text_content('main')[:500])
    check('map tab: today\'s jobs pinned', op.locator('.gm-map .gm-pin.p-job').count() == 2)
    check('map tab: route drawn', op.locator('.gm-map path.leaflet-interactive').count() >= 1)
    check('Ali not on shift → « Hors service »', 'Hors service' in op.text_content('main'))
    op.click('#mc-' + psql("select user_id from public.members where mechanic='Saleh'") + ' [data-act="map-path"]'); op.wait_for_timeout(1200)
    check('day path for Saleh', re.search(r'\d+ points depuis', op.text_content('main')) is not None, op.text_content('main')[-400:])
    check('map tab no sideways scroll', no_hscroll(op))
    op.screenshot(path=os.path.join(SC, 'team_map.png'))

    # ---------- 7. arrived, invoice on site ----------
    sp.click('.er [data-act="status"][data-v="place"]')
    check('« Sur place » saved', toast_has(sp, 'Sur place'))
    ok = False
    for _ in range(20):
        if psql("select status from public.tracks where job_id='j1'") == 'arrived': ok = True; break
        time.sleep(0.4)
    check('tracking link closed on arrival', ok)
    cp.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    try: cp.wait_for_function('() => /est arrivé/.test(document.getElementById("title").textContent)', timeout=12000); ok = True
    except Exception: ok = False
    check('client page: « Saleh est arrivé »', ok, cp.text_content('#title'))
    check('client page: van removed', cp.locator('.pin').count() == 1)
    sp.click('[data-act="invoice"][data-id="j1"]'); sp.wait_for_selector('#i-final', timeout=8000)
    sp.click('#i-final'); sp.wait_for_timeout(2500)
    num = psql("select data->'invoice'->>'number' from public.docs where path='jobs/j1'")
    check('mechanic finalizes invoice on site, number from the garage counter', num == 'F-0001', num)
    check('counter moved', psql("select data->>'next' from public.docs where path='meta/invoices'") == '2')

    # ---------- 8. office person ----------
    lc = ctx_for(br); lp = page_for(lc, 'lina'); login(lp, 'lina@garage.test', LINA_PW); lp.wait_for_selector('.acct', timeout=15000)
    lp.wait_for_timeout(600); lp.screenshot(path=os.path.join(SC, 'team_office.png'))
    check('office tabs: Agenda Clients Factures Carte', visible_tabs(lp) == ['Agenda', 'Clients', 'Factures', 'Carte'], visible_tabs(lp))
    lp.wait_for_timeout(800)
    check('office sees both jobs', 'Marie' in lp.text_content('main') and 'Paul' in lp.text_content('main'))
    check('office can book', lp.locator('[data-act="new"]').count() >= 1)
    check('office has no workday card', lp.locator('[data-act="sh-start"]').count() == 0)
    lp.goto(BASE + '#reglages'); lp.wait_for_timeout(500)
    check('office cannot open Réglages', lp.locator('.tab[data-t="agenda"][aria-current="page"]').count() == 1)
    lp.goto(BASE + '#equipe'); lp.wait_for_timeout(500)
    check('office cannot open team screen', lp.locator('#nw-name').count() == 0)
    # office presses « En route » for Ali's job: Ali is not on shift → link without position
    lp.goto(BASE + '#agenda'); lp.wait_for_selector('[data-act="open"][data-id="j2"]', timeout=8000); lp.click('[data-act="open"][data-id="j2"]')
    lp.wait_for_selector('.er-go'); check('office button says « En route : aviser Paul »', 'En route : aviser Paul' in lp.text_content('.er-go'))
    check('office is told whose position the client follows', 'position de Ali' in lp.text_content('.er'))
    lp.click('.er-go')
    check('office: text sent to Paul', toast_has(lp, 'Texto envoyé à Paul', 15000))
    lp.wait_for_selector('.er a.btn.steel', timeout=8000)
    check('no ETA without Ali\'s position (said plainly)', 'position du mécano n\'est pas encore connue' in lp.text_content('.er'), lp.text_content('.er'))

    # ---------- 9. GPS refused ----------
    ac = ctx_for(br, perms=False); ap = page_for(ac, 'ali'); login(ap, 'ali@garage.test', ALI_PW); ap.wait_for_selector('[data-act="sh-start"]', timeout=15000)
    ap.click('[data-act="sh-start"]'); ap.wait_for_selector('#sh-line', timeout=8000)
    try: ap.wait_for_function('() => /refuse/.test(document.getElementById("sh-line").textContent)', timeout=12000); ok = True
    except Exception: ok = False
    check('GPS refused: clear instruction', ok, ap.text_content('#sh-line'))
    ap.click('[data-act="sh-end"]'); check('Ali ends day', toast_has(ap, 'Bonne soirée'))

    # ---------- 10. end of day, access removed ----------
    sp.click('.tab[data-t="agenda"]'); sp.wait_for_selector('[data-act="sh-end"]', timeout=8000); sp.click('[data-act="sh-end"]')
    check('Saleh ends his day', toast_has(sp, 'n\'est plus envoyée'))
    check('no live position after the day', psql("select coalesce(lat::text,'none') from public.mech_live l join public.members m using (user_id) where m.mechanic='Saleh'") == 'none')
    op.goto(BASE + '#agenda'); op.goto(BASE + '#carte'); op.wait_for_timeout(1500); op.evaluate("document.querySelector('[data-act=\"map-fit\"]').click()")
    op.wait_for_timeout(10500)
    check('map: Saleh now « Hors service »', op.locator('#mc-' + psql("select user_id from public.members where mechanic='Saleh'") + ' .pillx').text_content() == 'Hors service')
    op.goto(BASE + '#equipe'); op.wait_for_selector('.eqp', timeout=8000)
    row = op.locator('.eqp', has_text='ali@garage.test'); row.locator('[data-act="eq-active"]').click()
    check('owner deactivates Ali', toast_has(op, 'Accès désactivé'))
    ac2 = ctx_for(br); ap2 = page_for(ac2, 'ali2'); login(ap2, 'ali@garage.test', ALI_PW); ap2.wait_for_timeout(2000)
    check('deactivated person cannot sign in', 'désactivé' in (ap2.text_content('#g-msg') or ''), ap2.text_content('#g-msg'))
    row = op.locator('.eqp', has_text='saleh@garage.test'); row.locator('[data-act="eq-pw"]').click()
    op.wait_for_selector('.created', timeout=8000)
    check('new password for Saleh shown once', 'Nouveau mot de passe pour Saleh' in op.text_content('.created'))
    op.click('[data-act="acct-out"]'); op.wait_for_selector('#gate #g-email', timeout=10000)
    check('sign out → login screen', 'Connexion' in op.text_content('#g-title'))

    check('no script errors', not ERRS, ERRS[:5])
    br.close()

n = sum(1 for _, ok in results if ok)
print(f'\n{n}/{len(results)} passed')
