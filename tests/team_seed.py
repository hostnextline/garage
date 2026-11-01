"""Shared setup for the team-version tests on the local Supabase copy: empty garage, owner, mechanics, office, treasurer, clients and jobs."""
import json, os, re, subprocess, hashlib, urllib.request, urllib.error, datetime

SC = os.path.dirname(os.path.abspath(__file__))
K = json.load(open(os.path.join(SC, 'stack/keys.json')))
BASE = 'http://127.0.0.1:8088/'
API = 'http://127.0.0.1:54321'
TODAY = datetime.date.today().isoformat()
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'

results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond)))
    print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def summary():
    n = sum(1 for _, ok in results if ok)
    print(f'\n{n}/{len(results)} passed'); return n == len(results)
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
        b = e.read().decode()
        try: j = json.loads(b)
        except Exception: j = {}
        return dict(j, _status=e.code, _body=b) if isinstance(j, dict) else {'_status': e.code, '_body': b}
def token(email, pw): return http('POST', API + '/auth/v1/token?grant_type=password', {'email': email, 'password': pw})['access_token']
def doc_set(tok, path, data): return http('POST', API + '/rest/v1/rpc/doc_set', {'p_path': path, 'p_data': data}, tok)
def doc(path):
    v = psql("select data from public.docs where path='%s'" % path.replace("'", "''"))
    return json.loads(v) if v else None
def fn(tok, name, body): return http('POST', API + '/functions/v1/' + name, body, tok)

def seed(stripe=False):
    """Empty garage → owner Hassan, mechanics Saleh and Ali, office Lina, treasurer Nadia; config with 2 open trucks; Marie (Saleh) and Paul (Ali) today."""
    psql("truncate public.members, public.docs, public.docs_deleted, public.mech_live, public.mech_positions, public.tracks, public.setup_codes, public.app_secrets cascade; delete from auth.users;")
    for t in ('client_links', 'stripe_events'):
        psql("do $$ begin if to_regclass('public.%s') is not null then execute 'truncate public.%s cascade'; end if; end $$;" % (t, t))
    urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:9200/__reset', data=b'{}', method='POST'))
    code = 'R4ND-0M7X-Q2PZ'
    psql("insert into public.setup_codes (code_hash) values ('%s')" % hashlib.sha256(code.replace('-', '').encode()).hexdigest())
    r = fn(None, 'members', {'action': 'setup', 'code': code, 'name': 'Hassan Banho', 'mechanic': 'Hassan', 'email': 'hassan@garage.test', 'password': 'Motdepasse-2026'})
    assert r and r.get('ok'), r
    otok = token('hassan@garage.test', 'Motdepasse-2026')
    pw = {'hassan': 'Motdepasse-2026'}
    for who, email, role, mech in (('Saleh Haddad', 'saleh@garage.test', 'mecano', 'Saleh'), ('Ali Ben', 'ali@garage.test', 'mecano', 'Ali'), ('Lina Bureau', 'lina@garage.test', 'bureau', None), ('Nadia Trésor', 'nadia@garage.test', 'tresorier', None)):
        r = fn(otok, 'members', {'action': 'create', 'name': who, 'email': email, 'role': role, 'mechanic': mech, 'password': 'Passe-' + email.split('@')[0] + '-26'})
        assert r and r.get('ok'), r
        pw[email.split('@')[0]] = 'Passe-' + email.split('@')[0] + '-26'
    # people who already know the app: their first-visit guided tour is done (test_tour.py removes this to see it)
    psql("insert into public.docs (path, data) select 'data/users/' || user_id || '/tour', '{\"seenAt\": 1}' from public.members on conflict (path) do nothing")
    fn(otok, 'members', {'action': 'secrets-set', 'ghlToken': 'pit-good-token', 'ghlLocation': 'loc123'})
    doc_set(otok, 'config/main', {'biz': {'name': 'Garage NextLine', 'phone': '514 555-0000'}, 'mechanics': ['Hassan', 'Saleh', 'Ali'], 'trucks': [{'id': 'c1', 'name': 'Camion 1', 'on': True, 'mech': 'Saleh'}, {'id': 'c2', 'name': 'Camion 2', 'on': True, 'mech': 'Ali'}, {'id': 'c3', 'name': 'Camion 3', 'on': False, 'mech': ''}],
                                  'rate': 120, 'taxesOn': True, 'startNo': 1, 'prefix': 'F-', 'services': [{'name': "Changement d'huile et filtre", 'price': 89.95}, {'name': 'Freins avant (plaquettes)', 'price': 249.0}, {'name': 'Inspection multipoints', 'price': 59.0}]})
    c1 = {'firstName': 'Marie', 'lastName': 'Tremblay', 'phone': '514 555-0101', 'email': 'marie@exemple.ca', 'address': '4520 rue Saint-Denis, Montréal', 'postal': 'H2J 2L3', 'geo': {'lat': 45.5265, 'lon': -73.5841}}
    c2 = {'firstName': 'Paul', 'lastName': 'Roy', 'phone': '438 555-0202', 'address': '100 rue Ontario Est, Montréal', 'postal': 'H2X 1H1', 'geo': {'lat': 45.5130, 'lon': -73.5600}}
    doc_set(otok, 'clients/c1', c1); doc_set(otok, 'clients/c2', c2)
    snap = lambda c, cid: {'id': cid, 'firstName': c['firstName'], 'lastName': c['lastName'], 'name': c['firstName'] + ' ' + c['lastName'], 'phone': c['phone'], 'address': c['address'], 'postal': c['postal'], 'geo': c['geo']}
    doc_set(otok, 'jobs/j1', {'date': TODAY, 'time': '14:00', 'durationMin': 60, 'mechanic': 'Saleh', 'truck': 'c1', 'clientId': 'c1', 'client': snap(c1, 'c1'), 'vehicle': {'make': 'Honda', 'model': 'Civic', 'year': '2018', 'displL': 2, 'cyl': 4, 'engine': '2,0 L 4 cyl.'}, 'services': ["Changement d'huile et filtre"], 'service': "Changement d'huile et filtre", 'status': 'planifie', 'createdAt': 1})
    doc_set(otok, 'jobs/j2', {'date': TODAY, 'time': '10:00', 'durationMin': 60, 'mechanic': 'Ali', 'truck': 'c2', 'clientId': 'c2', 'client': snap(c2, 'c2'), 'vehicle': {'make': 'Ford', 'model': 'F-150', 'year': '2017'}, 'services': ['Inspection multipoints'], 'service': 'Inspection multipoints', 'status': 'planifie', 'createdAt': 2})
    fn(otok, 'members', {'action': 'list'})   # (as after the owner opened « Équipe et accès » once: the agenda knows who has an account)
    return otok, pw

def ctx(browser, phone=False, geo=None, scheme='light'):
    c = browser.new_context(viewport={'width': 390 if phone else 1100, 'height': 844 if phone else 900}, timezone_id='America/Toronto', locale='fr-CA', has_touch=phone, color_scheme=scheme,
                            geolocation=geo, permissions=['geolocation'] if geo else [], **({'user_agent': IPHONE} if phone else {}))
    if os.environ.get('I18N_COLLECT'): c.add_init_script("window.__i18nCollect = 'http://127.0.0.1:9299/c';")   # (gathering every text shown, for the translation)
    if os.environ.get('I18N_LANG'): c.add_init_script("try { localStorage.setItem('gm.lang', '%s'); } catch(e){}" % os.environ['I18N_LANG'])
    c.route('https://tile.openstreetmap.org/**', lambda r: r.fulfill(status=200, content_type='image/png', body=b''))
    c.route('https://fonts.googleapis.com/**', lambda r: r.fulfill(status=200, content_type='text/css', body=''))
    c.route('https://fonts.gstatic.com/**', lambda r: r.abort())
    c.route('https://photon.komoot.io/**', lambda r: r.fulfill(status=200, content_type='application/json', body='{"type":"FeatureCollection","features":[]}'))
    for url, f in (('https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js', 'zxinglib/node_modules/@zxing/library/umd/index.min.js'),
                   ('https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js', 'xlsxlib/node_modules/xlsx/dist/xlsx.full.min.js')):
        body = open(os.path.join(SC, f), encoding='utf8').read()
        c.route(url, (lambda b: (lambda r: r.fulfill(status=200, content_type='application/javascript', body=b, headers={'Access-Control-Allow-Origin': '*'})))(body))
    return c
ERRS = []
def page(c, name):
    p = c.new_page()
    p.on('pageerror', lambda e: ERRS.append(name + ': ' + str(e)))
    p.on('console', lambda m: ERRS.append(name + ': ' + m.text) if m.type == 'error' and not re.search(r'realtime|websocket|WebSocket|ERR_|404|Failed to load resource|Failed to fetch|NetworkError|net::', m.text) else None)
    return p
def login(p, email, pw, wait='.acct, .ph-top, #tabbar', tour=False):
    # someone who already knows the app: no first-visit tour (test_tour.py passes tour=True to see it)
    if not tour: psql("insert into public.docs (path, data) select 'data/users/' || id || '/tour', '{\"seenAt\": 1}' from auth.users where email='%s' on conflict (path) do nothing" % email)
    p.goto(BASE + '#agenda'); p.wait_for_selector('#gate #g-email', timeout=15000)
    p.fill('#g-email', email); p.fill('#g-pw', pw); p.click('#g-go')
    p.wait_for_selector('#gate', state='detached', timeout=20000); p.wait_for_timeout(800)
def txt(p, sel):
    l = p.locator(sel)
    return re.sub(r'\s+', ' ', (l.first.text_content() or '').replace('\xa0', ' ').replace(' ', ' ')).strip() if l.count() else ''
def toast_has(p, text, ms=8000):
    try:
        p.wait_for_function('t => { const e = document.getElementById("toast"); return e && !e.hidden && e.textContent.includes(t); }', arg=text, timeout=ms); return True
    except Exception: return False
def wait_for(p, js, ms=15000, arg=None):
    try:
        if arg is None: p.wait_for_function(js, timeout=ms)
        else: p.wait_for_function(js, arg=arg, timeout=ms)
        return True
    except Exception: return False
def no_hscroll(p): return p.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')

def pick_roles(p, pre, roles):
    """tick exactly these role boxes (Équipe et accès: a person can have several roles)"""
    for r in ('mecano', 'bureau', 'tresorier', 'owner'):
        sel = '#%s-r-%s' % (pre, r)
        if p.locator(sel).count() and p.is_checked(sel) != (r in roles): p.click(sel)
