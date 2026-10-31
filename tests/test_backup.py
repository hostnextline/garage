"""Automatic backup: the backup server function (key, pages, what is left out), the nightly copy script, and putting data back."""
import json, os, subprocess, sys, tempfile, hashlib, secrets, shutil, glob, urllib.request, urllib.error
SC = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(os.path.dirname(SC), 'sauvegardes')
K = json.load(open(os.path.join(SC, 'stack/keys.json')))
API = 'http://127.0.0.1:54321'
results = []
def check(name, cond, detail=''):
    results.append((name, bool(cond))); print(('PASS ' if cond else 'FAIL ') + name + (('  -> ' + str(detail)[:300]) if detail and not cond else ''), flush=True)
def psql(sql):
    return subprocess.run(['psql', '-h', '127.0.0.1', '-p', '54322', '-U', 'postgres', '-Atq', '-c', sql], capture_output=True, text=True).stdout.strip()
def psql_file(path):
    return subprocess.run(['psql', '-h', '127.0.0.1', '-p', '54322', '-U', 'postgres', '-Atq', '-v', 'ON_ERROR_STOP=1', '-f', path], capture_output=True, text=True)
def post(key, body=None):
    h = {'Content-Type': 'application/json', 'apikey': K['anon'], 'Authorization': 'Bearer ' + K['anon']}
    if key is not None: h['x-backup-key'] = key
    req = urllib.request.Request(API + '/functions/v1/backup', data=json.dumps(body or {}).encode(), method='POST', headers=h)
    try:
        with urllib.request.urlopen(req) as r: return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e: return e.code, json.loads(e.read().decode() or '{}')
def docs_state():
    out = psql("select coalesce(json_object_agg(path, data order by path), '{}') from public.docs where path not like 'data/%'")
    return json.loads(out)
def run_backup(d, key, extra=None):
    env = dict(os.environ, SUPABASE_URL=API, SUPABASE_ANON=K['anon'], BACKUP_KEY=key, SAUVEGARDE_DIR=d, RETRY_WAIT='0.2'); env.update(extra or {})
    return subprocess.run([sys.executable, os.path.join(REPO, 'sauvegarder.py')], env=env, capture_output=True, text=True, timeout=300)

KEY = secrets.token_urlsafe(32)
before = docs_state()
psql("delete from public.app_secrets where name in ('BACKUP_KEY_SHA256','GHL_TOKEN_TEST')")
# a fake GoHighLevel key and a draft: they must NOT end up in the copy
psql("insert into public.app_secrets (name, value) values ('GHL_TOKEN_TEST', 'pit-SECRET-NE-PAS-COPIER')")
uid = psql("select user_id from public.members limit 1")
psql("insert into public.docs (path, data) values ('data/users/%s/draft-booking', '{\"note\":\"BROUILLON-PRIVE\"}') on conflict (path) do nothing" % uid)
# 40 receipt photos of ~300 kB (more than one page)
big = 'data:image/jpeg;base64,' + ('A' * 300000)
for i in range(40):
    psql("insert into public.docs (path, data) values ('receipts/t%02d', jsonb_build_object('img', 'data:image/jpeg;base64,' || repeat('A', 300000) || '%02d', 'expenseId', 'x%02d', 'at', %d))" % (i, i, i, i))
psql("insert into public.docs (path, data) values ('specs/2018-honda-civic-2-4', '{\"oilL\":4.4,\"oilVisc\":\"0W-20\"}')")

# ---------- the door ----------
st, b = post(None); check('no key → refused (401)', st == 401 and b.get('error') == 'not_allowed', (st, b))
st, b = post(KEY); check('key not set up on the server yet → refused', st == 401, (st, b))
psql("insert into public.app_secrets (name, value) values ('BACKUP_KEY_SHA256', '%s')" % hashlib.sha256(KEY.encode()).hexdigest())
st, b = post('x' * 40); check('wrong key → refused', st == 401, (st, b))
st, b = post(KEY[:-1] + ('A' if KEY[-1] != 'A' else 'B')); check('key with 1 character changed → refused', st == 401, st)
st, b = post(KEY)
check('right key → first page with the expected counts and the team', st == 200 and b.get('ok') and b['counts'].get('receipts') == 40 and b['counts'].get('jobs') == 3 and len(b['members']) == 5 and len(b['rows']) == 25 and b['next'], (st, {k: v for k, v in b.items() if k != 'rows'}))
check('no draft (data/users) and no key in the answer', 'BROUILLON-PRIVE' not in json.dumps(b) and 'SECRET-NE-PAS-COPIER' not in json.dumps(b) and not any(k.startswith('data') for k in b['counts']), b['counts'])

# ---------- the nightly copy ----------
d = tempfile.mkdtemp(prefix='sauv_')
os.makedirs(os.path.join(d, 'sauvegarde')); open(os.path.join(d, 'sauvegarde', '2025-01-01.json'), 'w').write('{}')   # a very old copy
r = run_backup(d, KEY)
check('nightly copy runs (exit 0) and says what it saved', r.returncode == 0 and r.stdout.startswith('OK ') and '40 reçus (40 nouveaux)' in r.stdout, r.stdout + r.stderr)
days = sorted(glob.glob(os.path.join(d, 'sauvegarde', '*.json')))
snap = json.load(open(days[-1], encoding='utf8')) if days else {}
now = docs_state()
want = {p for p in now if not p.startswith('receipts/')}
check('copy of the day: every document except receipt photos, exactly as in the base', {x['path'] for x in snap.get('documents', [])} == want and all(now[x['path']] == x['data'] for x in snap.get('documents', [])), len(snap.get('documents', [])))
check('receipt photos: one file each (40), identical to the base', len(glob.glob(os.path.join(d, 'recus', '*.json'))) == 40 and json.load(open(os.path.join(d, 'recus', 't07.json')))['data'] == now['receipts/t07'])
check('team list in the copy (5 people, roles)', len(snap.get('equipe', [])) == 5 and {m['role'] for m in snap['equipe']} >= {'owner', 'mecano'}, snap.get('equipe'))
whole = open(days[-1], encoding='utf8').read() + ''.join(open(f, encoding='utf8').read() for f in glob.glob(os.path.join(d, 'recus', '*.json')))
check('no password, GoHighLevel key, GPS position or draft in the files', 'SECRET-NE-PAS-COPIER' not in whole and 'BROUILLON-PRIVE' not in whole and 'password' not in whole.lower() and 'lat' not in json.dumps(snap.get('equipe')), '')
check('copies older than 90 days are cleaned out (history keeps them)', not os.path.exists(os.path.join(d, 'sauvegarde', '2025-01-01.json')))
check('copy of the day is small (receipts apart)', os.path.getsize(days[-1]) < 200000, os.path.getsize(days[-1]))
r2 = run_backup(d, KEY)
check('second run the same day: receipts not rewritten (0 nouveaux)', r2.returncode == 0 and '(0 nouveaux)' in r2.stdout, r2.stdout)
r3 = run_backup(d, 'mauvaise-cle-' + 'x' * 30)
check('copy with a wrong key fails loudly (exit ≠ 0 → GitHub sends an email)', r3.returncode != 0 and 'Refusé' in (r3.stderr + r3.stdout), r3.stderr[-200:])
r4 = run_backup(d, KEY, {'SUPABASE_URL': 'http://127.0.0.1:59999'})
check('server unreachable: retries, then fails loudly', r4.returncode != 0 and 'essai 4 raté' in r4.stdout and 'ne répond pas' in r4.stderr, (r4.stdout[-200:], r4.stderr[-200:]))

# ---------- putting data back ----------
psql("update public.docs set data = jsonb_set(data, '{status}', '\"annule\"') where path = 'jobs/j1'")
psql("delete from public.docs where path in ('clients/c1', 'receipts/t03', 'specs/2018-honda-civic-2-4')")
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
check('full restore: every document back exactly as in the copy (job, settings, engine sheet, receipt photo)', a.returncode == 0 and all(st2.get(p) == v for p, v in now.items()) and st2['receipts/t03'] == now['receipts/t03'], [p for p, v in now.items() if st2.get(p) != v][:5])
psql("insert into public.docs (path, data) values ('clients/apres', '{\"firstName\":\"Après\"}')")
a = psql_file(os.path.join(d, 'r2.sql'))
check('restore never erases what was added after the copy', a.returncode == 0 and 'clients/apres' in docs_state())
os.chdir(cwd)

# ---------- back to the original state ----------
psql("delete from public.docs where path like 'receipts/t%%' or path in ('specs/2018-honda-civic-2-4', 'clients/apres', 'data/users/%s/draft-booking')" % uid)
psql("delete from public.app_secrets where name in ('BACKUP_KEY_SHA256','GHL_TOKEN_TEST')")
after = docs_state()
check('local base back to its original state', after == before, [p for p in set(after) | set(before) if after.get(p) != before.get(p)][:5])
shutil.rmtree(d)
n = sum(1 for _, ok in results if ok)
print(f'\n{n}/{len(results)} passed'); sys.exit(0 if n == len(results) else 1)
