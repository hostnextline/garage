"""Remettre des données à partir d'une sauvegarde.

  python3 restaurer.py sauvegarde/2026-11-03.json                      -> restaurer.sql (tout le carnet de ce jour-là)
  python3 restaurer.py sauvegarde/2026-11-03.json --seulement jobs/     -> seulement les jobs
  python3 restaurer.py sauvegarde/2026-11-03.json --seulement clients/abc123

Le fichier restaurer.sql se colle dans Supabase > SQL Editor (ou Claude l'applique).
Il remet chaque document tel qu'il était ; il n'efface rien de ce qui a été ajouté après.
Les photos de reçus viennent du dossier recus/, les photos des jobs et les signatures du dossier photos/. Les comptes (mots de passe) ne sont pas dans la sauvegarde :
si le projet était perdu, on recrée les comptes dans « Équipe ».
"""
import json, os, sys


def lit(s):
    return "'" + s.replace("'", "''") + "'"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    only = sys.argv[sys.argv.index('--seulement') + 1] if '--seulement' in sys.argv else ''
    out = sys.argv[sys.argv.index('--sortie') + 1] if '--sortie' in sys.argv else 'restaurer.sql'
    snap = json.load(open(src, encoding='utf8'))
    base = os.path.dirname(os.path.dirname(os.path.abspath(src)))
    rows = list(snap['documents'])
    for key, folder in (('recus', 'recus'), ('photos', 'photos')):
        for p in snap.get(key, []):
            f = os.path.join(base, folder, p.split('/', 1)[1] + '.json')
            if os.path.exists(f):
                rows.append(json.load(open(f, encoding='utf8')))
            else:
                print('absent du dossier %s/ :' % folder, p)
    rows = [r for r in rows if r['path'].startswith(only)]
    if not rows:
        sys.exit('Rien à restaurer pour « %s ».' % only)
    with open(out, 'w', encoding='utf8') as f:
        f.write('-- Restauration de la sauvegarde du %s (%d documents%s)\nbegin;\n' % (snap['faite_le'], len(rows), ', seulement ' + only if only else ''))
        for r in rows:
            f.write('insert into public.docs (path, data) values (%s, %s::jsonb) on conflict (path) do update set data = excluded.data;\n'
                    % (lit(r['path']), lit(json.dumps(r['data'], ensure_ascii=False))))
        f.write('commit;\n')
    print('%s : %d documents à remettre' % (out, len(rows)))


if __name__ == '__main__':
    main()
