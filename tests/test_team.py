"""End-to-end test of the team version against the local Supabase copy:
real Postgres + rules, real Auth, real edge functions; GoHighLevel and the road router are local fakes."""
import json, os, re, subprocess, time, hashlib, urllib.request, datetime
from playwright.sync_api import sync_playwright
import io, base64, openpyxl

SC = os.path.dirname(os.path.abspath(__file__))
XLSX = open(os.path.join(SC, 'xlsxlib/node_modules/xlsx/dist/xlsx.full.min.js'), encoding='utf8').read()
ZXJS = open(os.path.join(SC, 'zxinglib/node_modules/@zxing/library/umd/index.min.js'), encoding='utf8').read()
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

def ctx_for(browser, geo=None, perms=True, simple=False):
    c = browser.new_context(viewport={'width': 390, 'height': 844}, timezone_id='America/Toronto', locale='fr-CA', has_touch=simple, **({'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'} if simple else {}),
                            geolocation=geo, permissions=(['geolocation', 'clipboard-read', 'clipboard-write'] if perms else []))
    if not simple: c.add_init_script("try{localStorage.setItem('gm.ui','full')}catch(e){}")
    c.route('https://tile.openstreetmap.org/**', lambda r: r.fulfill(status=200, content_type='image/png', body=b''))
    c.route('https://fonts.googleapis.com/**', lambda r: r.fulfill(status=200, content_type='text/css', body=''))
    c.route('https://cdn.jsdelivr.net/npm/@zxing/**', lambda r: r.fulfill(status=200, content_type='application/javascript', body=ZXJS))
    c.route('https://cdnjs.cloudflare.com/ajax/libs/xlsx/**', lambda r: r.fulfill(status=200, content_type='application/javascript', body=XLSX))
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
    p.goto(BASE + '#agenda'); p.wait_for_selector('#gate #g-email', timeout=10000)
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
    check('owner tabs: Accueil Agenda Clients Factures Trésorerie Carte Réglages', visible_tabs(op) == ['Accueil', 'Agenda', 'Clients', 'Factures', 'Trésorerie', 'Carte', 'Réglages'], visible_tabs(op))
    check('owner lands on the dashboard with his first name', op.locator('.tab[data-t="accueil"][aria-current="page"]').count() == 1 and op.text_content('h1') in ('Bonjour Hassan', 'Bonsoir Hassan'), op.text_content('h1'))
    check('owner dashboard: revenue + team on the road', 'Revenus facturés' in op.text_content('main') and op.locator('[aria-labelledby="d-road"]').count() == 1)
    check('owner (with a mechanic name) gets the workday card', op.locator('text=Début de journée').count() == 1)
    check('owner agenda no sideways scroll', no_hscroll(op))
    otok = token('hassan@garage.test', 'Motdepasse-2026')
    check('setup code used up', psql('select count(*) from public.setup_codes') == '0')
    r = doc_set(otok, 'config/main', {'biz': {'name': 'Garage NextLine'}, 'mechanics': ['Hassan', 'Saleh', 'Ali'], 'trucks': [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}], 'rate': 120, 'taxesOn': True, 'startNo': 1, 'prefix': 'F-'})
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
    check('mechanic tabs: Accueil Agenda Clients Factures', visible_tabs(sp) == ['Accueil', 'Agenda', 'Clients', 'Factures'], visible_tabs(sp))
    sp.click('.tab[data-t="accueil"]'); sp.wait_for_timeout(400)
    check('mechanic dashboard: his day and workday button, no money', 'Début de journée' in sp.text_content('main') and 'Revenus' not in sp.text_content('main') and 'À recevoir' not in sp.text_content('main') and sp.locator('.mcard').count() == 0)
    sp.click('.tab[data-t="agenda"]'); sp.wait_for_timeout(400)
    sp.wait_for_timeout(800)
    main = sp.text_content('main')
    check('mechanic sees his job (Marie)', 'Marie' in main, main[:300])
    check('mechanic does not see Ali\'s job (Paul)', 'Paul' not in main)
    check('no « + Réservation » for a mechanic', sp.locator('[data-act="new"]').count() == 0)
    check('no mechanic filter chips for a mechanic', sp.locator('[data-act="mech"]').count() == 0)
    check('first-time workday explanation (Loi 25)', 'gardées 30 jours' in main and 'Rien n\'est envoyé avant' in main)
    sp.goto(BASE + '#reglages'); sp.wait_for_timeout(500)
    check('mechanic cannot open Réglages (back to home)', sp.locator('.tab[data-t="accueil"][aria-current="page"]').count() == 1)
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
    try: op.wait_for_function('() => /Saleh Haddad/.test((document.querySelector("main")||{}).textContent||"")', timeout=12000); ok = True
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
    check('office tabs: Accueil Agenda Clients Factures Carte', visible_tabs(lp) == ['Accueil', 'Agenda', 'Clients', 'Factures', 'Carte'], visible_tabs(lp))
    lp.click('.tab[data-t="accueil"]')
    try: lp.wait_for_function('() => /Saleh Haddad/.test((document.querySelector("[aria-labelledby=d-road]")||{}).textContent||"")', timeout=10000); ok = True
    except Exception: ok = False
    check('office dashboard: who is working', ok and 'En journée' in lp.text_content('[aria-labelledby="d-road"]'), lp.text_content('main')[-400:])
    lp.screenshot(path=os.path.join(SC, 'team_office_dash.png'), full_page=True)
    lp.click('.tab[data-t="agenda"]'); lp.wait_for_timeout(500)
    lp.wait_for_timeout(800)
    check('office sees both jobs', 'Marie' in lp.text_content('main') and 'Paul' in lp.text_content('main'))
    check('office can book', lp.locator('[data-act="new"]').count() >= 1)
    check('office has no workday card', lp.locator('[data-act="sh-start"]').count() == 0)
    lp.goto(BASE + '#reglages'); lp.wait_for_timeout(500)
    check('office cannot open Réglages', lp.locator('.tab[data-t="accueil"][aria-current="page"]').count() == 1)
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

    # ---------- 9b. simple phone version (real logins) ----------
    def plus_rows(p): return p.evaluate("[...document.querySelectorAll('nav.ph-menu .ph-row b')].map(b=>b.textContent)")
    def ph_tabs(p): return p.evaluate("[...document.querySelectorAll('#tabbar .tab:not([hidden])')].sort((a,b)=>a.getBoundingClientRect().x-b.getBoundingClientRect().x).map(b=>b.dataset.t ? b.textContent.trim() : '+')")
    mc = ctx_for(br, perms=False, simple=True); mp = page_for(mc, 'ali-phone'); login(mp, 'ali@garage.test', ALI_PW); mp.wait_for_selector('.ph-list, .empty-card', timeout=15000)
    mp.wait_for_timeout(800)
    check('phone · mechanic: tabs « Ma journée », Clients, +, Factures, Plus', ph_tabs(mp) == ['Ma journée', 'Clients', '+', 'Factures', 'Plus'], ph_tabs(mp))
    check('phone · mechanic: his day only (Paul, not Marie), no free-time rows', mp.locator('.ph-job[data-id="j2"]').count() == 1 and mp.locator('.ph-job[data-id="j1"]').count() == 0 and mp.locator('.ph-gap').count() == 0)
    check('phone · mechanic: « Commencer ma journée » on top of his day', mp.locator('[data-act="sh-start"]').count() == 1)
    check('phone · mechanic: no mechanic filter', mp.locator('#ph-mech').count() == 0)
    check('phone · mechanic: no sideways scroll', no_hscroll(mp))
    mp.screenshot(path=os.path.join(SC, 'team_phone_mech.png'))
    mp.click('[data-act="ph-day"][data-v="1"]'); mp.wait_for_timeout(300)
    check('phone · mechanic: workday card only on today', mp.locator('[data-act="sh-start"]').count() == 0)
    mp.click('[data-act="ph-today"]'); mp.wait_for_timeout(300)
    mp.click('.ph-job[data-id="j2"]'); mp.wait_for_selector('.nextbtn', timeout=8000)
    check('phone · mechanic job: big button « Je suis arrivé » (job is en route)', mp.text_content('.nextbtn') == 'Je suis arrivé', mp.text_content('.nextbtn'))
    check('phone · mechanic job: tracking details shown, no duplicate buttons', mp.locator('.er').count() == 1 and mp.locator('.er [data-act="status"]').count() == 0)
    mp.click('.nextbtn')
    ok = False
    for _ in range(25):
        if psql("select data->>'status' from public.docs where path='jobs/j2'") == 'place' and psql("select status from public.tracks where job_id='j2'") == 'arrived': ok = True; break
        time.sleep(0.4)
    check('phone · mechanic: « Je suis arrivé » saved + client tracking closed (real base)', ok, psql("select data->>'status' from public.docs where path='jobs/j2'"))
    mp.wait_for_timeout(500)
    check('phone · mechanic job: next = « Terminer la job »', (mp.text_content('.nextbtn') or '') == 'Terminer la job', mp.text_content('.nextbtn'))
    mp.click('.tab[data-t="plus"]'); mp.wait_for_timeout(400)
    check('phone · mechanic Plus: dashboard + « Mes disponibilités » only (no map, team, hours, money, settings)', plus_rows(mp) == ['Tableau de bord', 'Mes disponibilités'], plus_rows(mp))
    # his own availability, through the real rules
    mp.click('a[href="#dispos"]'); mp.wait_for_selector('#av-week', timeout=8000)
    check('phone · mechanic: « Mes disponibilités », his week only (no other mechanic)', 'Ma semaine' in mp.text_content('#av-week') and mp.locator('[data-act="av-mech"]').count() == 0)
    mp.click('#av-week .switch[data-v="6"]'); mp.wait_for_timeout(1200)
    av = psql("select data->'week'->'6'->>'on' || '|' || (data->>'mechanic') from public.docs where path='avail/ali'")
    check('mechanic saves his own availability (Saturday on) in the real base', av == 'true|Ali', av)
    atok = token('ali@garage.test', ALI_PW)
    r = doc_set(atok, 'avail/saleh', {'mechanic': 'Saleh', 'week': None, 'off': []})
    check('a mechanic cannot change another mechanic\'s availability', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)
    r = doc_set(atok, 'avail/ali', {'mechanic': 'Saleh', 'week': None, 'off': []})
    check('… not even by renaming his own document', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)
    r = doc_set(atok, 'expenses/hack', {'total': 1})
    check('a mechanic cannot write expenses', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)
    mp.click('[data-act="av-reset"]'); mp.wait_for_timeout(1200)
    check('back to the garage hours (original state)', psql("select coalesce(data->>'week','null') from public.docs where path='avail/ali'") == 'null')
    mp.click('.tab[data-t="plus"]'); mp.wait_for_timeout(400)
    check('phone · mechanic Plus: who is signed in + sign out', 'Ali' in mp.text_content('main') and mp.locator('[data-act="acct-out"]').count() == 1)
    mp.click('.tab-new'); mp.wait_for_timeout(300)
    nm = mp.evaluate("[...document.querySelectorAll('#sheet .ph-row b')].map(b=>b.textContent)")
    check('phone · mechanic « + »: no booking', 'Nouvelle réservation' not in nm and 'Facture sur place' in nm, nm)
    mc.close()
    oc2 = ctx_for(br, perms=False, simple=True); op2 = page_for(oc2, 'owner-phone'); login(op2, 'hassan@garage.test', 'Motdepasse-2026'); op2.wait_for_selector('.dayhead', timeout=15000)
    op2.wait_for_timeout(800)
    check('phone · owner: tabs « Aujourd\'hui », Clients, +, Factures, Plus', ph_tabs(op2) == ["Aujourd'hui", 'Clients', '+', 'Factures', 'Plus'], ph_tabs(op2))
    check('phone · owner: sees both jobs + truck chips', op2.locator('.ph-job').count() == 2 and op2.locator('.chips.trucks [data-act="mech"]').count() == 4)
    op2.click('.tab[data-t="plus"]'); op2.wait_for_timeout(400)
    check('phone · owner Plus: dashboard, map, team, hours, availability, treasury, settings', plus_rows(op2) == ['Tableau de bord', 'Carte des mécanos', 'Équipe et accès', "Heures d'ouverture", 'Disponibilités des mécanos', 'Trésorerie', 'Réglages'], plus_rows(op2))
    op2.screenshot(path=os.path.join(SC, 'team_phone_plus.png'))
    op2.click('a[href="#carte"]'); op2.wait_for_selector('#map-slot', timeout=8000)
    check('phone · owner: map opens from Plus, back arrow to Plus', op2.locator('#map-slot').count() == 1 and op2.locator('[data-act="ph-back"]').count() == 1 and op2.locator('.tab[data-t="plus"][aria-current="page"]').count() == 1)
    op2.click('[data-act="ph-back"]'); op2.wait_for_timeout(400)
    op2.click('a[href="#equipe"]'); op2.wait_for_selector('.eqp', timeout=8000)
    check('phone · owner: team screen from Plus', op2.locator('.eqp').count() == 4 and no_hscroll(op2))
    op2.goto(BASE + '#reglages'); op2.wait_for_selector('#ph-setlist', timeout=8000)
    check('phone · owner: Réglages as a list (team link moved to Plus)', op2.locator('text=Gérer l\'équipe et les accès').count() == 0)
    oc2.close()

    # ---------- 9c. trucks: who leaves with which truck (office), with the real rules ----------
    TOM = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    doc_set(otok, 'jobs/j3', {'date': TOM, 'time': '09:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap(c1, 'c1'), 'vehicle': {'make': 'Honda'}, 'services': ['Diagnostic'], 'service': 'Diagnostic', 'status': 'planifie', 'createdAt': 3})
    lp.evaluate("d => { const S = window.__garageApi.S; S.screen = null; S.tab = 'agenda'; S.view = 'grid'; S.day = d; S.mech = ''; }", TOM); resync(lp); lp.evaluate("window.__garageApi.render()"); lp.wait_for_timeout(500)
    check('office: agenda columns are the trucks (Camion 3 closed)', [h.split('\n')[0] for h in lp.locator('.cal-head .colh').all_inner_texts()][:3] == ['Camion 1', 'Camion 2', 'Camion 3'] and 'Fermé' in lp.locator('.cal-head .colh').nth(2).inner_text(), lp.locator('.cal-head .colh').all_inner_texts())
    lp.select_option('#crewbox select[data-crew="c1"]', 'Ali'); lp.wait_for_timeout(2000)
    check('office sends Ali with Camion 1 tomorrow (saved for that day)', psql("select data->'crew'->>'c1' from public.docs where path='days/%s'" % TOM) == 'Ali')
    check('the planned job of Camion 1 follows: now Ali\'s (real base)', psql("select data->>'mechanic' from public.docs where path='jobs/j3'") == 'Ali')
    rd = http('GET', API + '/rest/v1/docs?select=path&path=eq.jobs/j3', token=atok)
    check('Ali can now read that job, through the rules', isinstance(rd, list) and len(rd) == 1, rd)
    lp.select_option('#crewbox select[data-crew="c1"]', 'Saleh'); lp.wait_for_timeout(2000)
    check('back to Saleh: the job follows back (original state)', psql("select data->>'mechanic' from public.docs where path='jobs/j3'") == 'Saleh')
    r = doc_set(token('lina@garage.test', LINA_PW), 'config/main', {'trucks': []})
    check('office cannot change the trucks (owner only)', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)

    # ---------- 9d. treasurer: his own screen ----------
    op.goto(BASE + '#equipe'); op.wait_for_selector('#nw-name', timeout=8000)
    check('team screen: role « Trésorier » offered and explained', 'tresorier' in op.evaluate("[...document.querySelectorAll('#nw-role option')].map(o => o.value)") and 'Trésorier' in op.text_content('.roles'))
    op.fill('#nw-name', 'Nadia Trésor'); op.fill('#nw-email', 'nadia@garage.test'); op.select_option('#nw-role', 'tresorier'); op.click('[data-act="eq-add"]')
    op.wait_for_selector('.created', timeout=10000); NADIA_PW = re.search(r'(Garage-[A-Z0-9]{4}-[A-Z0-9]{4})', op.text_content('.cred')).group(1); op.click('[data-act="eq-hidecred"]')
    check('treasurer account created', psql("select m.role from public.members m join auth.users u on u.id = m.user_id where u.email='nadia@garage.test'") == 'tresorier')
    tc = ctx_for(br, perms=False); tc.set_default_timeout(15000); tp = page_for(tc, 'nadia'); tp.set_viewport_size({'width': 1100, 'height': 900}); login(tp, 'nadia@garage.test', NADIA_PW)
    tp.wait_for_selector('#tr-label', timeout=15000); tp.wait_for_timeout(800)
    check('treasurer lands on Trésorerie; tabs: Clients, Factures, Trésorerie only', visible_tabs(tp) == ['Clients', 'Factures', 'Trésorerie'], visible_tabs(tp))
    tp.click('[data-act="tr-view"][data-v="rap"]'); tp.wait_for_timeout(400)
    check('treasurer report sees the invoice of the day (F-0001)', '1 facture' in tp.text_content('#rep-res'), tp.text_content('#rep-res'))
    tp.click('[data-act="tr-view"][data-v="dep"]'); tp.click('.top-in [data-act="exp-new"]'); tp.wait_for_selector('#x-total')
    tp.fill('#x-total', '57,49'); tp.fill('#x-vendor', 'Esso'); tp.select_option('#x-cat', 'essence'); tp.select_option('#x-truck', 'c2')
    tp.set_input_files('#x-file', os.path.join(SC, 'recu_test.jpg')); tp.wait_for_selector('#x-prev img', timeout=8000)
    tp.click('#x-save'); tp.wait_for_selector('#exp-list .xrow', timeout=10000); tp.wait_for_timeout(500)
    ex = psql("select (data->>'total') || '|' || (data->>'sub') || '|' || (data->>'truck') || '|' || (data->>'receipt' is not null) from public.docs where col='expenses'")
    rcp = psql("select length(data->>'img') < 330000 and (data->>'img') like 'data:image/jpeg%' from public.docs where col='receipts'")
    check('treasurer saves an expense with its receipt photo in the real base', ex == '57.49|50|c2|true' and rcp == 't', (ex, rcp))
    ttok = token('nadia@garage.test', NADIA_PW)
    r = doc_set(ttok, 'jobs/j3', {'status': 'annule'})
    check('treasurer cannot change a job', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)
    r = doc_set(ttok, 'config/main', {'biz': {'name': 'x'}})
    check('treasurer cannot change the settings', isinstance(r, dict) and r.get('_status') in (400, 401, 403), r)
    rd = http('GET', API + '/rest/v1/docs?select=path&col=eq.expenses', token=atok)
    check('a mechanic does not see the expenses', isinstance(rd, list) and len(rd) == 0, rd)
    tp.click('.tab[data-t="clients"]'); tp.wait_for_timeout(500)
    check('treasurer: clients without « + Nouveau client »', tp.locator('[data-act="cl-new"]').count() == 0 and 'Marie' in tp.text_content('main'))
    tp.click('.tab[data-t="tresor"]'); tp.wait_for_timeout(400); tp.click('[data-act="tr-view"][data-v="rap"]'); tp.wait_for_timeout(400)
    with tp.expect_download(timeout=15000) as dl: tp.click('[data-act="tr-xlsx"]')
    xp = os.path.join(SC, 'team_tresor.xlsx'); dl.value.save_as(xp)
    wb = openpyxl.load_workbook(xp, data_only=True)
    dep = [[c.value for c in r] for r in wb['Dépenses'].iter_rows()]
    check('treasurer downloads the Excel file (expense + invoice inside)', dl.value.suggested_filename.startswith('Trésorerie ') and len(dep) == 2 and dep[1][1] == 'Esso' and dep[1][3] == 'Camion 2' and len(list(wb['Revenus'].iter_rows())) == 2, (dl.value.suggested_filename, dep))
    tp.click('[data-act="tr-view"][data-v="dep"]'); tp.wait_for_timeout(300); tp.locator('#exp-list .xrow').first.click(); tp.wait_for_selector('#expform')
    tp.click('[data-act="exp-del"]'); tp.click('[data-act="exp-del"]'); tp.wait_for_timeout(1500)
    check('treasurer deletes the test expense and its photo (original state)', psql("select count(*) from public.docs where col in ('expenses','receipts')") == '0')
    tc.close()
    tc = ctx_for(br, perms=False, simple=True); tp = page_for(tc, 'nadia-phone'); login(tp, 'nadia@garage.test', NADIA_PW); tp.wait_for_selector('#tr-label', timeout=15000); tp.wait_for_timeout(600)
    check('treasurer on a phone: Trésorerie, Clients, +, Factures, Plus', tp.evaluate("[...document.querySelectorAll('#tabbar .tab:not([hidden])')].sort((a,b)=>a.getBoundingClientRect().x-b.getBoundingClientRect().x).map(b=>b.dataset.t || '+')") == ['tresor', 'clients', '+', 'factures', 'plus'])
    tc.close()

    # ---------- 9e. VIN through the garage server (NHTSA base, fake here) + engine sheet in the real base ----------
    CIV = '2HGFC2F58JH512345'
    r = http('POST', API + '/functions/v1/vehicle', {'vin': CIV})
    check('vehicle server: refused without a garage login', isinstance(r, dict) and r.get('_status') == 401, r)
    stok = token('saleh@garage.test', SALEH_PW)
    r = http('POST', API + '/functions/v1/vehicle', {'vin': 'ABC123'}, stok)
    check('vehicle server: a wrong VIN gets « 17 lettres et chiffres »', isinstance(r, dict) and r.get('_status') == 400 and '17 lettres' in r.get('_body', ''), r)
    r = http('POST', API + '/functions/v1/vehicle', {'vin': CIV.lower()}, stok)
    rr = (r or {}).get('r') or {}
    check('vehicle server: mechanic decodes → 2018 HONDA Civic 2.0 L 4 cyl., only the useful fields sent back', (r or {}).get('ok') and rr.get('Make') == 'HONDA' and rr.get('ModelYear') == '2018' and rr.get('DisplacementL') == '2.0' and len(rr) == 16 and 'VIN' not in rr, r)
    r = http('POST', API + '/functions/v1/vehicle', {'vin': CIV}, ttok)
    check('vehicle server: the treasurer may decode too (read only, harmless)', (r or {}).get('ok'), r)
    vc = ctx_for(br); vp = page_for(vc, 'saleh-vin'); vp.set_viewport_size({'width': 1100, 'height': 900}); login(vp, 'saleh@garage.test', SALEH_PW); vp.wait_for_selector('.acct', timeout=15000); vp.wait_for_timeout(800)
    vp.evaluate("() => { const S = window.__garageApi.S; S.tab = 'agenda'; S.screen = 'job'; S.jobId = 'j3'; window.__garageApi.render(); }"); vp.wait_for_timeout(400)
    vp.click('[data-act="scan-job"]'); vp.wait_for_selector('#scan-body'); vp.wait_for_timeout(600)
    vp.click('[data-act="scan-type"]'); vp.fill('#scan-in', CIV); vp.click('[data-act="scan-typed"]')
    try: vp.wait_for_selector('#scan-body .vehsum', timeout=12000); okv = True
    except Exception: okv = False
    body = (vp.text_content('#scan-body') or '').replace('\xa0', ' ')
    check('team · mechanic: typed VIN decoded through the garage server: 2018 Honda Civic LX, 2,0 L 4 cyl.', okv and '2018 Honda Civic LX' in body and '2,0 L 4 cyl.' in body, body[:200])
    vp.click('[data-act="scan-use"]'); toast_has(vp, 'Véhicule mis à jour'); vp.wait_for_timeout(800)
    vj = json.loads(psql("select data->'vehicle' from public.docs where path='jobs/j3'") or '{}')
    check('team · mechanic: « Mettre sur la job » saved in the real base (VIN, model, engine)', vj.get('vin') == CIV and vj.get('model') == 'Civic' and vj.get('engine') == '2,0 L 4 cyl.' and vj.get('drive') == 'Traction avant', vj)
    vp.click('#speccard [data-act="spec-edit"]'); vp.wait_for_selector('#specform'); vp.fill('#sp-oilL', '4,4'); vp.click('[data-act="sp-visc"][data-v="0W-20"]'); vp.fill('#sp-oilFilter', 'PH7317'); vp.click('#sp-save')
    check('team · mechanic: engine sheet saved', toast_has(vp, 'Fiche technique enregistrée'))
    vp.wait_for_timeout(600)
    spd = json.loads(psql("select data from public.docs where path='specs/2018-honda-civic-2-4'") or '{}')
    check('team · engine sheet in the real base: 4.4 L 0W-20 PH7317, « by » Saleh', spd.get('oilL') == 4.4 and spd.get('oilVisc') == '0W-20' and spd.get('oilFilter') == 'PH7317' and spd.get('by') == 'Saleh', spd)
    check('team · mechanic sees « Huile : 4,4 L · 0W-20 · filtre PH7317 » on the job', 'Huile : 4,4 L · 0W-20 · filtre PH7317' in (vp.text_content('#speccard') or '').replace('\xa0', ' '))
    rd = http('GET', API + '/rest/v1/docs?select=path&col=eq.specs', token=atok)
    check('team · the other mechanic (Ali) reads the engine sheet', isinstance(rd, list) and len(rd) == 1, rd)
    r = doc_set(ttok, 'specs/2018-honda-civic-2-4', {'oilL': 99})
    check('team · treasurer cannot change an engine sheet', isinstance(r, dict) and r.get('_status') in (400, 401, 403) and psql("select data->>'oilL' from public.docs where path='specs/2018-honda-civic-2-4'") == '4.4', r)
    vc.close()
    psql("delete from public.docs where col='specs'")
    doc_set(otok, 'jobs/j3', dict(json.loads(psql("select data from public.docs where path='jobs/j3'")), vehicle={'make': 'Honda'}))
    check('engine sheet and job vehicle back to the original state', psql("select count(*) from public.docs where col='specs'") == '0' and psql("select data->'vehicle'->>'vin' from public.docs where path='jobs/j3'") == '')

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
