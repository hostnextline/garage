# Garage mobile — sources

- `carnet.html` : l'app (même fichier pour claude.ai et pour le site).
- `web/` : version rapide (`build.py` → index.html) et version équipe (`build_team.py` → equipe/ : supa.js = connexion + carnet partagé, equipe.js = rôles, journée, En route, carte, accès ; suivi.html = page du client).
- `supabase/` : base de données (migrations/) et fonctions serveur (functions/en-route, functions/members).
- Téléphone (< 700 px) : version simple automatique (Aujourd'hui, Clients, +, Factures, Plus) ; « Version complète » dans Plus. `web/pwa.json` + `web/icons/` (`mkicons.py`) = icône sur l'écran d'accueil.
- `tests/` : tests navigateur (Playwright, `bash tests/regress.sh` les lance tous) et `tests/stack/` = copie locale de Supabase pour tester
  (Postgres 16 + PostgREST 12.2.3 + Supabase Auth v2.180.0 + Deno, GoHighLevel et itinéraires simulés).
  `node keys.js > keys.json`, appliquer base.sql puis la migration, lancer Auth/PostgREST, puis `bash up.sh`.
