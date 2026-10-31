"""Copie de la nuit : télécharge tout le carnet du garage et l'écrit dans ce dépôt privé.

  sauvegarde/AAAA-MM-JJ.json  le carnet du jour (jobs, clients, factures, réglages, horaire, dépenses, fiches techniques, équipe)
  recus/<id>.json             une photo de reçu par fichier (écrit une seule fois : l'historique git garde tout)

Aucun mot de passe : GitHub signe chaque exécution (jeton OIDC, valable quelques minutes) et le serveur du garage
n'accepte que ce dépôt privé. Variables : SUPABASE_URL, SUPABASE_ANON (clé publique). Sortie ≠ 0 = la sauvegarde a échoué
(GitHub envoie alors un courriel).
"""
import datetime, glob, json, os, sys, time, urllib.error, urllib.request

URL = os.environ.get('SUPABASE_URL', '').rstrip('/')
ANON = os.environ.get('SUPABASE_ANON', '')
HERE = os.environ.get('SAUVEGARDE_DIR') or os.path.dirname(os.path.abspath(__file__))
KEEP_DAYS = int(os.environ.get('KEEP_DAYS', '90'))   # fichiers du jour gardés ; les plus vieux restent dans l'historique git


def github_token():
    """Jeton signé par GitHub pour cette exécution (on en redemande un à chaque appel : il expire vite)."""
    u, t = os.environ.get('ACTIONS_ID_TOKEN_REQUEST_URL'), os.environ.get('ACTIONS_ID_TOKEN_REQUEST_TOKEN')
    if not (u and t):
        sys.exit('Pas de jeton GitHub : ce script tourne seulement dans GitHub Actions (permissions: id-token: write).')
    req = urllib.request.Request(u + ('&' if '?' in u else '?') + 'audience=garage-sauvegarde', headers={'Authorization': 'bearer ' + t})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())['value']


def call(after):
    for attempt in range(4):
        try:
            req = urllib.request.Request(URL + '/functions/v1/backup', data=json.dumps({'after': after}).encode(), method='POST',
                                         headers={'Content-Type': 'application/json', 'apikey': ANON, 'Authorization': 'Bearer ' + ANON, 'x-gh-oidc': github_token()})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (401, 403):
                sys.exit('Refusé par le serveur (%s) : %s' % (e.code, msg))
            err = 'HTTP %s %s' % (e.code, msg)
        except Exception as e:  # réseau, projet en réveil après une pause…
            err = str(e)
        print('essai %d raté : %s' % (attempt + 1, err), flush=True)
        time.sleep(float(os.environ.get('RETRY_WAIT', '15')) * (attempt + 1))   # un projet gratuit en pause peut prendre un moment à répondre
    sys.exit('Le serveur ne répond pas : ' + err)


def download():
    first = call('')
    rows, counts, members, at, nxt = list(first['rows']), first.get('counts') or {}, first.get('members') or [], first['at'], first['next']
    while nxt:
        page = call(nxt); rows += page['rows']; nxt = page['next']
    return rows, counts, members, at


def main():
    if not URL:
        sys.exit('SUPABASE_URL est requis.')
    for tries in range(2):   # quelqu'un peut écrire pendant la copie : on recommence une fois si les comptes ne collent pas
        rows, counts, members, at = download()
        got = {}
        for r in rows:
            c = r['path'].rsplit('/', 1)[0]; got[c] = got.get(c, 0) + 1
        if got == counts:
            break
        print('les comptes ne collent pas, on recommence', got, counts, flush=True)
    else:
        sys.exit('Sauvegarde incomplète : reçu %s, attendu %s' % (got, counts))

    os.makedirs(os.path.join(HERE, 'sauvegarde'), exist_ok=True); os.makedirs(os.path.join(HERE, 'recus'), exist_ok=True)
    docs = [r for r in rows if not r['path'].startswith('receipts/')]
    recus = [r for r in rows if r['path'].startswith('receipts/')]
    new_recus = 0
    for r in recus:
        p = os.path.join(HERE, 'recus', r['path'].split('/', 1)[1] + '.json')
        txt = json.dumps(r, ensure_ascii=False, sort_keys=True)
        old = open(p, encoding='utf8').read() if os.path.exists(p) else None
        if old != txt:
            open(p, 'w', encoding='utf8').write(txt); new_recus += 1
    day = at[:10]
    snap = {'faite_le': at, 'nombre': counts, 'equipe': members, 'documents': docs, 'recus': sorted(r['path'] for r in recus)}
    open(os.path.join(HERE, 'sauvegarde', day + '.json'), 'w', encoding='utf8').write(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True))
    limit = (datetime.date.fromisoformat(day) - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    for f in glob.glob(os.path.join(HERE, 'sauvegarde', '*.json')):
        if os.path.basename(f)[:10] < limit:
            os.remove(f)
    print('OK %s : %d documents (%s), %d reçus (%d nouveaux), %d personnes dans l\'équipe'
          % (day, len(docs), ', '.join('%s %d' % kv for kv in sorted(counts.items())), len(recus), new_recus, len(members)), flush=True)


if __name__ == '__main__':
    main()
