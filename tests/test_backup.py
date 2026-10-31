"""Automatic backup: the backup server function (key, pages, what is left out), the nightly copy script, and putting data back."""
import json, os, subprocess, sys, tempfile, shutil, glob, urllib.request, urllib.error
SC = os.path.dirname(os.path.abspath(__file__))
REPO = '/home/claude/garage/sauvegardes-repo'
K = json.load(open(os.path.join(SC, 'stack/keys.json')))
API = 'http://127.0.0.1:54321'
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def psql(sql):
    return subprocess.run(['psql', '-h', '127.0.0.1', '-p', '54322', '-U', 'postgres', '-Atq', '-c', sql], capture_output=True, text=True).stdout.strip()
def psql_file(path):
    return subprocess.run(['psql', '-h', '127.0.0.1', '-p', '54322', '-U', 'postgres', '-Atq', '-v', 'ON_ERROR_STOP=1', '-f', path], capture_output=True, text=True)
def docs_state():
    out = psql("select coalesce(json_object_agg(path, data order by path), '{}') from public.docs where path not like 'data/%'")
    return json.loads(out)

# ---------- a stand-in for GitHub: signs tokens like GitHub Actions does (same claims) ----------
import threading, http.server, time as _t, jwt as pyjwt, base64
from cryptography.hazmat.primitives.asymmetric import rsa
GH_KEY, BAD_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048), rsa.generate_private_key(public_exponent=65537, key_size=2048)
def b64u(n): return base64.urlsafe_b64encode(n.to_bytes((n.bit_length() + 7) // 8, 'big')).rstrip(b'=').decode()
PUB = GH_KEY.public_key().public_numbers()
KID = 'gh-' + os.urandom(4).hex()   # GitHub rotates its keys: a new key always comes with a new id
JWKS = {'keys': [{'kty': 'RSA', 'kid': KID, 'alg': 'RS256', 'use': 'sig', 'n': b64u(PUB.n), 'e': b64u(PUB.e)}]}
ISS = 'http://127.0.0.1:9205'
GOOD = {'iss': ISS, 'aud': 'garage-sauvegarde', 'repository': 'hostnextline/garage-sauvegardes', 'repository_id': '1441054755', 'repository_owner_id': '243496564', 'ref': 'refs/heads/main', 'event_name': 'schedule'}
def tok(key=None, **chg):
    c = dict(GOOD, iat=int(_t.time()), nbf=int(_t.time()) - 5, exp=int(_t.time()) + 300); c.update(chg)
    c = {k: v for k, v in c.items() if v is not None}
    return pyjwt.encode(c, key or GH_KEY, algorithm='RS256', headers={'kid': KID})
MINT = {'claims': {}}
class GH(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith('/.well-known/jwks'): body = json.dumps(JWKS)
        elif self.path.startswith('/mint') and self.headers.get('Authorization') == 'bearer run-token' and 'audience=garage-sauvegarde' in self.path: body = json.dumps({'value': tok(**MINT['claims'])})
        else: self.send_response(403); self.end_headers(); return
        self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(body.encode())
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 9205), GH); threading.Thread(target=srv.serve_forever, daemon=True).start()
def post(token, body=None):
    h = {'Content-Type': 'application/json', 'apikey': K['anon'], 'Authorization': 'Bearer ' + K['anon']}
    if token is not None: h['x-gh-oidc'] = token
    req = urllib.request.Request(API + '/functions/v1/backup', data=json.dumps(body or {}).encode(), method='POST', headers=h)
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode() or '{}')
def run_backup(d, claims=None, extra=None):
    MINT['claims'] = claims or {}
    env = {k: v for k, v in os.environ.items() if not k.startswith('ACTIONS_')}
    env.update(SUPABASE_URL=API, SUPABASE_ANON=K['anon'], SAUVEGARDE_DIR=d, RETRY_WAIT='0.2', ACTIONS_ID_TOKEN_REQUEST_URL=ISS + '/mint?api-version=2.0', ACTIONS_ID_TOKEN_REQUEST_TOKEN='run-token')
    env.update(extra or {})
    return subprocess.run([sys.executable, os.path.join(REPO, 'sauvegarder.py')], env=env, capture_output=True, text=True, timeout=300)

from team_seed import seed as _seed
_seed()   # a garage with its team, clients and jobs (the other tests leave the base empty)
psql("insert into public.docs (path, data) values ('jobs/j3', '{\"date\":\"2026-11-02\",\"mechanic\":\"Ali\",\"status\":\"planifie\"}') on conflict do nothing")
before = docs_state()
psql("delete from public.app_secrets where name in ('BACKUP_KEY_SHA256','GHL_TOKEN_TEST')")
psql("insert into public.app_secrets (name, value) values ('GHL_TOKEN_TEST', 'pit-SECRET-NE-PAS-COPIER')")
uid = psql("select user_id from public.members limit 1")
psql("insert into public.docs (path, data) values ('data/users/%s/draft-booking', '{\"note\":\"BROUILLON-PRIVE\"}') on conflict (path) do nothing" % uid)
for i in range(40):
    psql("insert into public.docs (path, data) values ('receipts/t%02d', jsonb_build_object('img', 'data:image/jpeg;base64,' || repeat('A', 300000) || '%02d', 'expenseId', 'x%02d', 'at', %d))" % (i, i, i, i))
psql("insert into public.docs (path, data) values ('photos/j1__p1', jsonb_build_object('jobId', 'j1', 'kind', 'avant', 'img', 'data:image/jpeg;base64,' || repeat('B', 250000))), ('photos/j1__sig1', jsonb_build_object('jobId', 'j1', 'kind', 'signature', 'img', 'data:image/png;base64,QUJD', 'name', 'Marie'))")
psql("insert into public.docs (path, data) values ('specs/2018-honda-civic-2-4', '{\"oilL\":4.4,\"oilVisc\":\"0W-20\"}')")

# ---------- the door: only a token signed by GitHub for THIS private repo, main branch ----------
st, b = post(None); check('no token → refused (401)', st == 401 and b.get('error') == 'not_allowed', (st, b))
st, b = post('pas-un-jeton'); check('garbage token → refused', st == 401, st)
for label, t in [('signed with another key', tok(BAD_KEY)), ('another repository (a fork, a copy)', tok(repository='pirate/garage-sauvegardes')),
                 ('same name but another repository number (deleted and recreated)', tok(repository_id='999')), ('another owner', tok(repository_owner_id='1')),
                 ('another branch', tok(ref='refs/heads/test')), ('another audience', tok(aud='autre-chose')), ('expired', tok(exp=int(_t.time()) - 120, iat=int(_t.time()) - 600, nbf=int(_t.time()) - 600)),
                 ('another issuer', tok(iss='https://evil.example')), ('missing repository number', tok(repository_id=None))]:
    st, b = post(t); check('token %s → refused' % label, st == 401, (st, b))
st, b = post('eyJhbGciOiJub25lIn0.' + base64.urlsafe_b64encode(json.dumps(dict(GOOD, exp=int(_t.time()) + 300)).encode()).rstrip(b'=').decode() + '.')
check('unsigned token (alg none) → refused', st == 401, st)
st, b = post(tok())
check('GitHub-signed token for the private repo → first page with the expected counts and the team', st == 200 and b.get('ok') and b['counts'].get('receipts') == 40 and b['counts'].get('jobs') == 3 and len(b['members']) == 5 and len(b['rows']) == 25 and b['next'], (st, {k: v for k, v in b.items() if k != 'rows'}))
check('no draft (data/users) and no key in the answer', 'BROUILLON-PRIVE' not in json.dumps(b) and 'SECRET-NE-PAS-COPIER' not in json.dumps(b) and not any(k.startswith('data') for k in b['counts']), b['counts'])

# ---------- the nightly copy ----------
d = tempfile.mkdtemp(prefix='sauv_')
os.makedirs(os.path.join(d, 'sauvegarde')); open(os.path.join(d, 'sauvegarde', '2025-01-01.json'), 'w').write('{}')   # a very old copy
r = run_backup(d)
check('nightly copy runs (exit 0) and says what it saved', r.returncode == 0 and r.stdout.startswith('OK ') and '40 reçus (40 nouveaux)' in r.stdout, r.stdout + r.stderr)
days = sorted(glob.glob(os.path.join(d, 'sauvegarde', '*.json')))
snap = json.load(open(days[-1], encoding='utf8')) if days else {}
now = docs_state()
want = {p for p in now if not p.startswith('receipts/')}
want = {p for p in want if not p.startswith('photos/')}
check('job photos and signatures: one file each in photos/ (2), not in the copy of the day', len(glob.glob(os.path.join(d, 'photos', '*.json'))) == 2 and json.load(open(os.path.join(d, 'photos', 'j1__sig1.json')))['data']['name'] == 'Marie' and sorted(snap.get('photos', [])) == ['photos/j1__p1', 'photos/j1__sig1'])
check('copy of the day: every document except pictures, exactly as in the base', {x['path'] for x in snap.get('documents', [])} == want and all(now[x['path']] == x['data'] for x in snap.get('documents', [])), len(snap.get('documents', [])))
check('receipt photos: one file each (40), identical to the base', len(glob.glob(os.path.join(d, 'recus', '*.json'))) == 40 and json.load(open(os.path.join(d, 'recus', 't07.json')))['data'] == now['receipts/t07'])
check('team list in the copy (5 people, roles)', len(snap.get('equipe', [])) == 5 and {m['role'] for m in snap['equipe']} >= {'owner', 'mecano'}, snap.get('equipe'))
whole = open(days[-1], encoding='utf8').read() + ''.join(open(f, encoding='utf8').read() for f in glob.glob(os.path.join(d, 'recus', '*.json')))
check('no password, GoHighLevel key, GPS position or draft in the files', 'SECRET-NE-PAS-COPIER' not in whole and 'BROUILLON-PRIVE' not in whole and 'password' not in whole.lower() and 'lat' not in json.dumps(snap.get('equipe')), '')
check('copies older than 90 days are cleaned out (history keeps them)', not os.path.exists(os.path.join(d, 'sauvegarde', '2025-01-01.json')))
check('copy of the day is small (receipts apart)', os.path.getsize(days[-1]) < 200000, os.path.getsize(days[-1]))
r2 = run_backup(d)
check('second run the same day: receipts not rewritten (0 nouveaux)', r2.returncode == 0 and '(0 nouveaux)' in r2.stdout, r2.stdout)
r3 = run_backup(d, {'repository': 'pirate/garage'})
check('copy run from another repository fails loudly (exit ≠ 0 → GitHub sends an email)', r3.returncode != 0 and 'Refusé' in (r3.stderr + r3.stdout), r3.stderr[-200:])
r3b = run_backup(d, extra={'ACTIONS_ID_TOKEN_REQUEST_URL': ''})
check('outside GitHub Actions (no signed token): stops with a clear message', r3b.returncode != 0 and 'GitHub Actions' in r3b.stderr, r3b.stderr[-200:])
r4 = run_backup(d, extra={'SUPABASE_URL': 'http://127.0.0.1:59999'})
check('server unreachable: retries, then fails loudly', r4.returncode != 0 and 'essai 4 raté' in r4.stdout and 'ne répond pas' in r4.stderr, (r4.stdout[-200:], r4.stderr[-200:]))

# ---------- putting data back ----------
psql("update public.docs set data = jsonb_set(data, '{status}', '\"annule\"') where path = 'jobs/j1'")
psql("delete from public.docs where path in ('clients/c1', 'receipts/t03', 'specs/2018-honda-civic-2-4', 'photos/j1__p1')")
psql("update public.docs set data = '{}'::jsonb where path = 'config/main'")
broken = docs_state()
check('(damage done: job changed, client + receipt + engine sheet deleted, settings emptied)', broken.get('jobs/j1', {}).get('status') == 'annule' and 'clients/c1' not in broken and broken['config/main'] == {})
cwd = os.getcwd(); os.chdir(d)
o = subprocess.run([sys.executable, os.path.join(REPO, 'restaurer.py'), days[-1], '--seulement', 'clients/', '--sortie', 'r1.sql'], capture_output=True, text=True)
check('restore only clients: 1 SQL file with the clients only', o.returncode == 0 and open('r1.sql', encoding='utf8').read().count('insert into') == len([p for p in now if p.startswith('clients/')]), o.stdout + o.stderr)
a = psql_file(os.path.join(d, 'r1.sql'))
st1 = docs_state()
check('clients back, the rest still as it was (job still cancelled)', a.returncode == 0 and st1.get('clients/c1') == now['clients/c1'] and st1['jobs/j1'].get('status') == 'annule', a.stderr)
o = subprocess.run([sys.executable, os.path.join(REPO, 'restaurer.py'), days[-1], '--sortie', 'r2.sql'], capture_output=True, text=True)
a = psql_file(os.path.join(d, 'r2.sql'))
st2 = docs_state()
check('full restore: every document back exactly as in the copy (job, settings, engine sheet, receipt photo)', a.returncode == 0 and all(st2.get(p) == v for p, v in now.items()) and st2['receipts/t03'] == now['receipts/t03'] and st2.get('photos/j1__p1') == now['photos/j1__p1'], [p for p, v in now.items() if st2.get(p) != v][:5])
psql("insert into public.docs (path, data) values ('clients/apres', '{\"firstName\":\"Après\"}')")
a = psql_file(os.path.join(d, 'r2.sql'))
check('restore never erases what was added after the copy', a.returncode == 0 and 'clients/apres' in docs_state())
os.chdir(cwd)

# ---------- back to the original state ----------
psql("delete from public.docs where path like 'photos/j1__%%'")
psql("delete from public.docs where path like 'receipts/t%%' or path in ('specs/2018-honda-civic-2-4', 'clients/apres', 'data/users/%s/draft-booking')" % uid)
psql("delete from public.app_secrets where name in ('BACKUP_KEY_SHA256','GHL_TOKEN_TEST')")
srv.shutdown()
after = docs_state()
check('local base back to its original state', after == before, [p for p in set(after) | set(before) if after.get(p) != before.get(p)][:5])
shutil.rmtree(d)
n = sum(1 for _, ok in results if ok)
print(f'\n{n}/{len(results)} passed'); sys.exit(0 if n == len(results) else 1)
